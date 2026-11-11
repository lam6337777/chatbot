"""Bộ điều phối: route → tool → câu trả lời.

`respond()` là generator sinh các sự kiện cho SSE:
    {"type": "meta", "intent": ...}
    {"type": "delta", "text": ...}         # nối dần thành câu trả lời
    {"type": "products", "items": [...]}   # thẻ sản phẩm để widget hiển thị
    {"type": "handoff"}                    # gợi ý chuyển sang chat với nhân viên

Giọng điệu: nhân viên CSKH lịch sự — xưng "em", gọi khách "anh/chị", mở đầu "Dạ", kết "ạ".
Câu trả lời dựng từ dữ liệu (không qua LLM) cũng được "gõ" dần từng cụm từ để tự nhiên như LLM stream.
"""
import logging
import re
import time

from . import backend, llm, policies, tools
from .router import Route, route
from .text import has_any, norm, vnd

log = logging.getLogger("pf_bot")

PERSONA = """Bạn là nhân viên tư vấn của PF. Shoes — cửa hàng giày thể thao chính hãng bán online.
Quy tắc bắt buộc:
- Trả lời bằng tiếng Việt lịch sự, ân cần như nhân viên chăm sóc khách hàng: xưng "em", gọi khách là "anh/chị",
  mở đầu bằng "Dạ," và kết câu bằng "ạ" khi phù hợp.
- Ngắn gọn: tối đa 5 câu hoặc 5 gạch đầu dòng.
- Nếu tài liệu có điều kiện hoặc NGOẠI LỆ (ví dụ "ngoại trừ…", "không áp dụng…", "chỉ được…"), BẮT BUỘC nêu rõ trong câu trả lời.
- CHỈ dùng thông tin trong phần TÀI LIỆU. Nếu tài liệu không có câu trả lời, xin lỗi vì chưa có thông tin đó và mời anh/chị bấm "Chat với nhân viên".
- Không bịa số điện thoại, email, địa chỉ, giá, mã giảm giá hay thời hạn.
- Mỗi con số phải đi kèm ĐÚNG ý nghĩa như trong tài liệu: phân biệt "thời hạn" (khách được yêu cầu trong bao lâu)
  với "thời gian xử lý / hoàn tiền" (shop xử lý mất bao lâu). Không ghép con số của chính sách này sang chính sách khác.
- Nếu các tài liệu ghi khác nhau, ưu tiên tài liệu chính sách chuyên biệt (ví dụ "Chính sách đổi trả & hoàn tiền")
  hơn phần "Câu hỏi thường gặp".
- Không dùng tiếng Trung, tiếng Anh hay ngôn ngữ khác ngoài tiếng Việt (trừ tên sản phẩm).
- Không nhắc tới số mục/điều khoản của tài liệu (như "mục 9"); diễn đạt lại nội dung."""


def _say(text):
    return {"type": "delta", "text": text}


# ── Hiệu ứng gõ chữ cho câu trả lời dựng sẵn ───────────────────────────────────
# Cụm **đậm** và [link](...) giữ nguyên một khối để widget không hiện ký tự markdown dở dang
_TOKENS = re.compile(r"\*\*.+?\*\*[^\s*]*\s*|\[[^\]]+\]\([^)]+\)\s*|\S+\s*|\s+")


def _typewrite(text: str):
    tokens = _TOKENS.findall(text)
    # ~45 cụm/giây với câu ngắn; câu dài gõ nhanh hơn để tổng thời gian không quá ~2.5s
    delay = 0.022 if len(tokens) < 80 else max(0.008, 2.5 / len(tokens))
    for tok in tokens:
        yield _say(tok)
        time.sleep(delay)


def _paced(events):
    """Chuyển delta dựng sẵn thành nhiều delta nhỏ; delta từ LLM (live) đi thẳng."""
    first = True
    for ev in events:
        if ev["type"] == "delta" and not ev.get("live"):
            if first:
                time.sleep(0.35)  # khoảng "đang soạn" ngắn trước khi trả lời
                first = False
            yield from _typewrite(ev["text"])
        else:
            if ev["type"] == "delta":
                first = False
                ev = _say(ev["text"])
            yield ev


def _history_msgs(history: list[dict]) -> list[dict]:
    out = []
    for m in history:
        role = "assistant" if m.get("role") == "bot" else "user"
        out.append({"role": role, "content": (m.get("content") or "")[:600]})
    return out


_CONDENSE_PROMPT = """Bạn viết lại câu hỏi MỚI NHẤT của khách thành một câu hỏi ĐẦY ĐỦ, tự hiểu được mà không cần đọc đoạn hội thoại.
- Bổ sung từ hội thoại trước những gì câu mới đang ám chỉ: tên/hãng/loại giày, size, mức giá, tỉnh thành, mã đơn, chủ đề chính sách.
  Ví dụ: trước đó hỏi "giày chạy bộ Nike dưới 2 triệu", giờ hỏi "còn size 44 không" → "Giày chạy bộ Nike dưới 2 triệu còn size 44 không".
- Nếu câu mới đã đủ nghĩa hoặc chuyển sang chủ đề khác, giữ NGUYÊN câu đó.
- Không trả lời câu hỏi, không thêm thông tin không có trong hội thoại. Viết bằng tiếng Việt.
Trả về JSON: {"question": "..."}"""


def _condense(question: str, history: list[dict]) -> str:
    """Câu hỏi nối tiếp ("thế còn size 44?", "ship về Hà Nội thì sao?") → câu hỏi độc lập để định tuyến/tra cứu đúng."""
    if not any(m.get("role") == "user" for m in history):
        return question
    lines = []
    for m in history[-6:]:
        who = "Khách" if m.get("role") == "user" else "Shop"
        lines.append(f"{who}: {(m.get('content') or '').strip()[:300]}")
    try:
        out = llm.complete_json(_CONDENSE_PROMPT, "HỘI THOẠI:\n" + "\n".join(lines) + f"\n\nCÂU MỚI: {question}", max_tokens=120)
    except llm.LLMUnavailable:
        return question
    q = (out.get("question") or "").strip()
    # Câu viết lại bất thường (rỗng, quá dài) → dùng câu gốc
    return q if 0 < len(q) <= 300 else question


def _llm_answer(question: str, docs: list[str], history: list[dict], extra: str = ""):
    context = "\n\n---\n\n".join(docs)
    system = f"{PERSONA}\n\nTÀI LIỆU:\n{context}{chr(10) + extra if extra else ''}"
    yielded = False
    # Một lượt hội thoại mẫu để model nhỏ bắt chước giọng "Dạ … ạ" (chỉ dẫn trong system prompt là chưa đủ)
    example = [
        {"role": "user", "content": "Shop có giao hàng toàn quốc không?"},
        {"role": "assistant", "content": "Dạ, shop có giao hàng trên toàn quốc ạ. Thời gian nhận hàng thường từ 1–5 ngày tùy khu vực, "
                                         "anh/chị yên tâm đặt hàng nhé!"},
    ]
    try:
        for piece in llm.stream_text(system, [*example, *_history_msgs(history), {"role": "user", "content": question}]):
            yielded = True
            yield {"type": "delta", "text": piece, "live": True}
    except llm.LLMUnavailable:
        if not yielded:
            # Không gọi được model: trả nguyên đoạn tài liệu liên quan nhất thay vì báo lỗi
            yield _say("Dạ, em xin lỗi, trợ lý AI đang gặp chút trục trặc ạ. Em gửi anh/chị thông tin liên quan trong chính sách của shop:\n\n")
            yield _say(docs[0][:900] if docs else "Anh/chị vui lòng thử lại sau ít phút hoặc chat với nhân viên giúp em nhé ạ.")


# ── Từng ý định ────────────────────────────────────────────────────────────────

def _shipping(r: Route):
    province = r.params.get("province")
    q = tools.shipping_quote(province)
    threshold = vnd(q.get("freeShippingThreshold"))
    days = q.get("estimatedDays") or "3–5 ngày"
    if province:
        yield _say(f"Dạ, phí giao hàng tới **{province}** là **{vnd(q['fee'])}**, thời gian nhận hàng dự kiến khoảng {days} ạ.\n")
    else:
        yield _say(f"Dạ, phí giao hàng tiêu chuẩn của shop là **{vnd(q['fee'])}** (khoảng {days}), một số tỉnh/thành có mức riêng ạ.\n"
                   f"Anh/chị cho em xin tỉnh/thành nhận hàng để em báo phí chính xác nhé.\n")
    yield _say(f"Đặc biệt, đơn hàng từ **{threshold}** được **miễn phí vận chuyển** ạ.")


def _vouchers(_: Route):
    vs = tools.vouchers()
    if not vs:
        yield _say("Dạ, hiện shop chưa có mã giảm giá công khai nào ạ. Anh/chị theo dõi trang chủ để không bỏ lỡ ưu đãi sắp tới nhé!")
        return
    yield _say("Dạ, hiện shop đang có các mã giảm giá sau ạ:\n")
    for v in vs[:6]:
        yield _say(f"- {tools.voucher_line(v)}\n")
    yield _say("\nAnh/chị nhập mã ở bước **giỏ hàng** hoặc **thanh toán**, hệ thống sẽ tự kiểm tra điều kiện của đơn ạ.")


def _need_login():
    yield _say("Dạ, anh/chị vui lòng **đăng nhập** để em tra cứu đơn hàng giúp mình ạ. "
               "Sau khi đăng nhập, anh/chị cũng có thể xem tại mục [Đơn hàng của tôi](/account/orders).")


def _my_orders(_: Route, ctx):
    if not ctx["user"]:
        yield from _need_login()
        return
    orders = tools.my_orders(ctx["jwt"])
    if not orders:
        yield _say("Dạ, em chưa thấy đơn hàng nào trong tài khoản của anh/chị ạ. "
                   "Anh/chị ghé [trang sản phẩm](/products) để chọn đôi ưng ý nhé!")
        return
    yield _say("Dạ, đây là các đơn hàng gần đây của anh/chị ạ:\n")
    for o in orders:
        yield _say(f"- {tools.order_line(o)}\n")
    yield _say("\nAnh/chị bấm vào mã đơn để xem chi tiết và hành trình giao hàng nhé.")


def _order_detail(r: Route, ctx):
    if not ctx["user"]:
        yield from _need_login()
        return
    code = r.params["code"]
    try:
        o = tools.order_detail(code, ctx["jwt"])
    except backend.BackendError as e:
        if e.status in (403, 404):
            yield _say(f"Dạ, em chưa tìm thấy đơn **{code}** trong tài khoản của anh/chị ạ. "
                       "Anh/chị kiểm tra lại mã đơn giúp em nhé.")
            return
        raise
    status = tools.ORDER_STATUS.get(o["status"], o["status"])
    pay = tools.PAYMENT_STATUS.get(o.get("paymentStatus"), o.get("paymentStatus"))
    yield _say(f"Dạ, đơn [#{o['orderCode']}](/account/orders/{o['orderCode']}) của anh/chị hiện đang ở trạng thái **{status}** ({pay}) ạ.\n")
    for it in (o.get("items") or [])[:5]:
        yield _say(f"- {it['productName']} · size {it['size']} × {it['quantity']}\n")
    yield _say(f"\nTổng thanh toán: **{vnd(o.get('totalAmount'))}**")
    hist = o.get("statusHistory") or []
    if hist and hist[-1].get("note"):
        yield _say(f"\nCập nhật gần nhất: {hist[-1]['note']}.")
    if o["status"] == "PENDING":
        yield _say("\nĐơn chưa được xác nhận nên anh/chị vẫn có thể hủy trong trang chi tiết đơn ạ.")


def _cancel(r: Route, ctx):
    if not ctx["user"]:
        yield from _need_login()
        return
    code = r.params.get("code")
    if code:
        try:
            o = tools.order_detail(code, ctx["jwt"])
        except backend.BackendError:
            yield _say(f"Dạ, em chưa tìm thấy đơn **{code}** trong tài khoản của anh/chị ạ.")
            return
        if o["status"] == "CANCELLED":
            yield _say(f"Dạ, đơn **{code}** đã được hủy trước đó rồi ạ, anh/chị không cần thao tác thêm.")
        elif o["status"] == "PENDING":
            yield _say(f"Dạ, đơn **{code}** đang chờ xác nhận nên anh/chị có thể tự hủy ngay ạ: mở [chi tiết đơn](/account/orders/{code}) "
                       f"rồi bấm **Hủy đơn hàng**. Mã giảm giá (nếu có) sẽ được hoàn lại lượt dùng.")
        else:
            status = tools.ORDER_STATUS.get(o["status"], o["status"])
            yield _say(f"Dạ, đơn **{code}** đang ở trạng thái **{status}** nên hệ thống chưa cho phép tự hủy ạ. "
                       f"Anh/chị bấm \"Chat với nhân viên\" để shop hỗ trợ trực tiếp giúp mình nhé.")
            yield {"type": "handoff"}
        return
    pending = [o for o in tools.my_orders(ctx["jwt"], limit=10) if o["status"] == "PENDING"]
    if not pending:
        yield _say("Dạ, hiện anh/chị không có đơn nào đang chờ xác nhận ạ. "
                   "Với đơn đã xác nhận hoặc đang giao, nhân viên shop sẽ hỗ trợ hủy giúp mình.")
        yield {"type": "handoff"}
        return
    yield _say("Dạ, đây là các đơn đang chờ xác nhận mà anh/chị có thể tự hủy ạ:\n")
    for o in pending:
        yield _say(f"- {tools.order_line(o)}\n")
    yield _say("\nAnh/chị mở đơn cần hủy và bấm **Hủy đơn hàng** giúp em nhé.")


def _describe_filters(p: dict) -> str:
    parts = []
    if p.get("keyword"):
        parts.append(f"“{p['keyword']}”")
    if p.get("category"):
        parts.append(f"giày {p['category'].lower()}")
    if p.get("brand"):
        parts.append(p["brand"])
    if p.get("size"):
        parts.append(f"size {p['size']}")
    if p.get("min_price") and p.get("max_price"):
        parts.append(f"giá {vnd(p['min_price'])}–{vnd(p['max_price'])}")
    elif p.get("max_price"):
        parts.append(f"dưới {vnd(p['max_price'])}")
    elif p.get("min_price"):
        parts.append(f"từ {vnd(p['min_price'])}")
    if p.get("on_sale"):
        parts.append("đang giảm giá")
    return " ".join(parts)


def _product_search(r: Route, ctx):
    p = dict(r.params)
    # Câu hỏi nối tiếp ("còn size 43 không?", "rẻ hơn chút?") kế thừa bộ lọc của lượt trước
    last = ctx["state"].get("last_product_params") or {}
    if last and not any(p.get(k) for k in ("keyword", "brand", "category")):
        p = {**last, **p}
    ctx["state"]["last_product_params"] = p

    res = tools.search_products(**p)
    desc = _describe_filters({**p, "keyword": None if res["relaxed"] else p.get("keyword")})
    if res["total"] == 0:
        yield _say(f"Dạ, em rất tiếc, hiện shop chưa có mẫu {desc or 'phù hợp'} ạ. "
                   "Anh/chị thử nới khoảng giá, đổi size hoặc xem [tất cả sản phẩm](/products) giúp em nhé.")
        return
    # Toàn bộ lời dẫn đứng trước danh sách thẻ sản phẩm (widget hiển thị thẻ dưới cùng)
    if res["relaxed"] == "keyword":
        if not desc:
            yield _say(f"Dạ, hiện shop chưa có mẫu “{p['keyword']}” ạ. Em gửi anh/chị tham khảo vài mẫu đang bán chạy nhé:")
            yield {"type": "products", "items": res["products"]}
            return
        lead = f"Dạ, hiện shop chưa có mẫu “{p['keyword']}”, nhưng có **{res['total']}** mẫu {desc} ạ."
    else:
        lead = f"Dạ, em tìm được **{res['total']}** mẫu{(' ' + desc) if desc else ''} phù hợp với anh/chị ạ."
    if res["total"] > len(res["products"]):
        missing = [w for k, w in (("size", "size"), ("max_price", "khoảng giá"), ("category", "môn thể thao")) if not p.get(k)]
        hint = f" Anh/chị cho em biết thêm {' và '.join(missing[:2])} để em lọc sát hơn nhé." if missing else ""
        lead += f" Em gửi anh/chị {len(res['products'])} mẫu nổi bật bên dưới.{hint}"
    yield _say(lead)
    if p.get("size"):
        out = [x["name"] for x in res["products"] if x.get("sizeStock") == 0]
        if out:
            yield _say(f"\nLưu ý: mẫu {', '.join(out)} đang tạm hết size {p['size']} ạ.")
    yield {"type": "products", "items": res["products"]}


# Bảng quy đổi trong Data_policy/size_guild.txt.txt (chiều dài chân cm → size EU/VN)
_SIZE_TABLE = [(23.5, "38"), (24.0, "39"), (24.5, "40"), (25.0, "41"), (26.0, "42"), (27.0, "43"), (28.0, "44")]


def _size_from_cm(question: str):
    m = re.search(r"(\d{2}(?:[.,]\d)?)\s*(?:cm|phân|phan)", question.lower())
    if not m:
        return None
    cm = float(m.group(1).replace(",", "."))
    if not 20 <= cm <= 32:
        return None
    for limit, size in _SIZE_TABLE:
        if cm <= limit:
            return cm, size
    return cm, None


def _size_answer(cm: float, size: str | None):
    if size is None:
        yield _say(f"Dạ, chân dài {cm:g}cm lớn hơn bảng size hiện có của shop (tối đa size 44, khoảng 28cm) ạ. "
                   "Anh/chị bấm \"Chat với nhân viên\" để được tư vấn mẫu phù hợp giúp em nhé.")
        return
    yield _say(f"Dạ, với chiều dài chân **{cm:g}cm**, anh/chị nên chọn **size {size}** (size EU/VN) ạ.\n")
    yield _say("Một vài lưu ý nhỏ:\n"
               "- Chân bè hoặc mu bàn chân cao: nên tăng thêm 0.5–1 size.\n"
               "- Nếu phân vân giữa 2 size, anh/chị chọn size lớn hơn sẽ thoải mái hơn.\n"
               "- Nên đo chân vào cuối ngày vì lúc này bàn chân giãn nở lớn nhất ạ.")


def _policy(r: Route, question: str, ctx):
    topic = r.params.get("topic", "general")
    if topic == "size":
        hit = _size_from_cm(question)
        if hit:
            yield from _size_answer(*hit)
            return
    if topic == "payment" and has_any(norm(question), ["vnpay", "the", "chuyen khoan", "momo", "cod", "hinh thuc",
                                                         "thanh toan bang", "thanh toan the nao", "tra truoc", "online"]):
        yield _say(TEMPLATES["payment_methods"])
        return
    docs = policies.retrieve(question, topic)
    extra = ""
    if topic == "payment":
        # Thực tế hệ thống (OrderService chỉ nhận COD) — ưu tiên hơn tài liệu chính sách cũ
        extra = ("THÔNG TIN CẬP NHẬT (ưu tiên hơn tài liệu): hiện website CHỈ nhận thanh toán khi nhận hàng (COD). "
                 "Thanh toán online qua VNPay/thẻ ngân hàng đang được tích hợp, CHƯA dùng được.")
    if topic == "shipping":
        try:
            q = tools.shipping_quote(None)
            extra = (f"Dữ liệu phí ship hiện tại: mặc định {vnd(q['fee'])}, giao {q.get('estimatedDays')}; "
                     f"miễn phí ship cho đơn từ {vnd(q.get('freeShippingThreshold'))}.")
        except backend.BackendError:
            pass
    yield from _llm_answer(question, docs, ctx["history"], extra)


def _general(question: str, ctx):
    docs = policies.retrieve(question, "general", k=2)
    yield from _llm_answer(question, docs, ctx["history"])


TEMPLATES = {
    "payment_methods": "Dạ, hiện PF. Shoes nhận **thanh toán khi nhận hàng (COD)** ạ: anh/chị được kiểm tra giày rồi mới thanh toán cho nhân viên giao hàng.\n"
                       "Thanh toán online qua **VNPay / thẻ ngân hàng** đang được tích hợp và sẽ sớm ra mắt. "
                       "Anh/chị cứ yên tâm đặt hàng, không cần chuyển khoản trước ạ!",
    "greeting": "Dạ, PF. Shoes xin chào anh/chị ạ! Em là trợ lý tư vấn của shop. "
                "Em có thể giúp anh/chị tìm giày theo size, giá, môn thể thao; báo phí ship, mã giảm giá; "
                "tra cứu đơn hàng hoặc giải đáp chính sách đổi trả, bảo hành. Anh/chị cần em hỗ trợ gì ạ?",
    "thanks": "Dạ, em cảm ơn anh/chị ạ! Nếu cần thêm thông tin gì, anh/chị cứ nhắn em nhé.",
    "refuse": "Dạ, em xin lỗi, em chỉ có thể hỗ trợ các câu hỏi về sản phẩm, đơn hàng và chính sách của PF. Shoes thôi ạ.",
    "off_topic": "Dạ, câu hỏi này nằm ngoài phạm vi hỗ trợ của em rồi ạ. "
                 "Em có thể giúp anh/chị tìm giày, tra cứu đơn hàng hoặc giải đáp chính sách của shop nhé!",
    "handoff": "Dạ, em chuyển anh/chị sang **nhân viên tư vấn** ngay ạ. "
               "Anh/chị bấm \"Chat với nhân viên\" bên dưới, shop sẽ phản hồi sớm nhất có thể.",
}


def _respond(question: str, history: list[dict], jwt: str | None, state: dict):
    t0 = time.time()
    user = backend.current_user(jwt)
    history = history[-6:]  # 3 lượt hỏi–đáp gần nhất
    ctx = {"jwt": jwt if user else None, "user": user, "history": history, "state": state}
    original = question
    question = _condense(question, history)
    if question != original:
        log.info("condensed: %r -> %r", original, question)
    r = route(question)
    log.info("route=%s params=%s source=%s (%.2fs)", r.intent, r.params, r.source, time.time() - t0)
    yield {"type": "meta", "intent": r.intent}

    try:
        if r.intent in TEMPLATES:
            yield _say(TEMPLATES[r.intent])
            if r.intent == "handoff":
                yield {"type": "handoff"}
        elif r.intent == "shipping":
            yield from _shipping(r)
        elif r.intent == "vouchers":
            yield from _vouchers(r)
        elif r.intent == "my_orders":
            yield from _my_orders(r, ctx)
        elif r.intent == "order_detail":
            yield from _order_detail(r, ctx)
        elif r.intent == "cancel_order":
            yield from _cancel(r, ctx)
        elif r.intent == "product_search":
            yield from _product_search(r, ctx)
        elif r.intent == "policy":
            yield from _policy(r, question, ctx)
        else:
            yield from _general(question, ctx)
    except backend.BackendError as e:
        log.error("backend error: %s %s", e.status, e.message)
        yield _say("\nDạ, em xin lỗi, hệ thống cửa hàng đang bận nên em chưa lấy được dữ liệu ạ. "
                   "Anh/chị vui lòng thử lại sau ít phút giúp em nhé.")
    log.info("answered in %.2fs", time.time() - t0)


def respond(question: str, history: list[dict], jwt: str | None, state: dict):
    """Generator sự kiện trả lời cho một câu hỏi (đã có hiệu ứng gõ chữ)."""
    yield from _paced(_respond(question, history, jwt, state))

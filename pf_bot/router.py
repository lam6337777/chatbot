"""Nhận diện ý định + tách tham số.

Ưu tiên quy tắc (regex trên chuỗi đã bỏ dấu) vì nhanh và chính xác hơn model 3B;
chỉ gọi LLM khi câu không khớp quy tắc nào.
"""
import re
from dataclasses import dataclass, field

from . import backend, llm
from .text import has_any, norm

PROVINCES = [
    "Hà Nội", "Hồ Chí Minh", "Hải Phòng", "Đà Nẵng", "Cần Thơ", "Huế", "An Giang", "Bắc Ninh", "Cà Mau",
    "Cao Bằng", "Đắk Lắk", "Điện Biên", "Đồng Nai", "Đồng Tháp", "Gia Lai", "Hà Tĩnh", "Hưng Yên", "Khánh Hòa",
    "Lai Châu", "Lạng Sơn", "Lào Cai", "Lâm Đồng", "Nghệ An", "Ninh Bình", "Phú Thọ", "Quảng Ngãi", "Quảng Ninh",
    "Quảng Trị", "Sơn La", "Tây Ninh", "Thái Nguyên", "Thanh Hóa", "Tuyên Quang", "Vĩnh Long",
]
_PROVINCE_ALIASES = {
    "hn": "Hà Nội", "ha noi": "Hà Nội", "thu do": "Hà Nội",
    "hcm": "Hồ Chí Minh", "tphcm": "Hồ Chí Minh", "tp hcm": "Hồ Chí Minh", "sai gon": "Hồ Chí Minh", "saigon": "Hồ Chí Minh",
    "sg": "Hồ Chí Minh", "da nang": "Đà Nẵng", "dn": "Đà Nẵng", "hai phong": "Hải Phòng", "can tho": "Cần Thơ", "hue": "Huế",
    # Tỉnh cũ đã sáp nhập (07/2025) — vẫn hay được khách dùng
    "binh duong": "Hồ Chí Minh", "ba ria": "Hồ Chí Minh", "vung tau": "Hồ Chí Minh", "bien hoa": "Đồng Nai",
    "nha trang": "Khánh Hòa", "da lat": "Lâm Đồng", "vinh": "Nghệ An", "ha long": "Quảng Ninh", "buon ma thuot": "Đắk Lắk",
    "quy nhon": "Gia Lai", "bac giang": "Bắc Ninh", "hai duong": "Hải Phòng", "nam dinh": "Ninh Bình", "thai binh": "Hưng Yên",
    "vinh phuc": "Phú Thọ", "long an": "Tây Ninh", "tien giang": "Đồng Tháp", "ben tre": "Vĩnh Long", "kien giang": "An Giang",
    "soc trang": "Cần Thơ", "bac lieu": "Cà Mau", "quang nam": "Đà Nẵng", "quang binh": "Quảng Trị", "kon tum": "Quảng Ngãi",
}

# Từ khóa theo danh mục (giá trị là tên danh mục trong DB)
_CATEGORY_ALIASES = {
    "chay bo": "Chạy bộ", "running": "Chạy bộ", "marathon": "Chạy bộ", "di chay": "Chạy bộ",
    "bong da": "Bóng đá", "da bong": "Bóng đá", "san co": "Bóng đá", "futsal": "Bóng đá", "football": "Bóng đá",
    "bong ro": "Bóng rổ", "basketball": "Bóng rổ",
    "truot van": "Trượt ván", "skate": "Trượt ván", "skateboard": "Trượt ván",
    "luyen tap": "Luyện tập", "tap gym": "Luyện tập", "gym": "Luyện tập", "training": "Luyện tập",
    "sneaker": "Giày Sneaker", "sneakers": "Giày Sneaker",
    "giay luoi": "Giày lười", "loafer": "Giày lười", "slip on": "Giày lười",
    "thoi trang": "Thời trang", "di choi": "Thời trang", "lifestyle": "Thời trang",
}

_PRODUCT_WORDS = ["giay", "mau", "san pham", "con hang", "het hang", "size", "sz", "gia", "mua",
                  "nike", "jordan", "adidas", "re nhat", "dat nhat", "moi nhat", "hot", "ban chay", "goi y", "tu van"]
_STOPWORDS = set("""sale hot shop co ban khong ko k nao gi la cho minh toi em anh chi a ah oi nhe nha voi va hay hoac the
con hang het mau doi giay san pham can mua muon tim kiem xem gia bao nhieu tien re dat nhat duoi tren tu den khoang
tam size sz co so chan loai nhung cac mot vay a? ạ duoc dang sale giam the nao nhu gi khong?""".split())


@dataclass
class Route:
    intent: str  # product_search | shipping | vouchers | my_orders | order_detail | cancel_order | policy | handoff | greeting | thanks | refuse | general
    params: dict = field(default_factory=dict)
    source: str = "rule"


# ── Tham số ────────────────────────────────────────────────────────────────────
_MONEY = re.compile(r"(\d+(?:[.,]\d+)?)\s*(trieu|tr|cu|k|nghin|ngan|d|vnd|dong)?(\d)?(?!\w)")


def _money_values(t: str) -> list[int]:
    vals = []
    for m in _MONEY.finditer(t):
        num, unit, tail = m.group(1), m.group(2), m.group(3)
        if not unit:
            raw = num.replace(".", "").replace(",", "")
            if raw.isdigit() and int(raw) >= 10000:  # "500000" (không đơn vị) vẫn là tiền
                vals.append(int(raw))
            continue
        x = float(num.replace(",", "."))
        if unit in ("trieu", "tr", "cu"):
            x *= 1_000_000
            if tail:  # 1tr5 = 1.500.000
                x += int(tail) * 100_000
        elif unit in ("k", "nghin", "ngan"):
            x *= 1_000
        vals.append(int(x))
    return vals


_RANGE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:-|den|toi)\s*(\d+(?:[.,]\d+)?)\s*(trieu|tr|cu|k|nghin|ngan)(?!\w)")


def parse_price(t: str):
    m = _RANGE.search(t)
    if m:  # "từ 1 đến 3 triệu", "1-2tr": đơn vị áp cho cả hai số
        a = _money_values(f"{m.group(1)} {m.group(3)}")[0]
        b = _money_values(f"{m.group(2)} {m.group(3)}")[0]
        return min(a, b), max(a, b)
    vals = _money_values(t)
    if not vals:
        return None, None
    if len(vals) >= 2 and has_any(t, ["tu", "den", "toi", "-", "khoang"]):
        return min(vals[:2]), max(vals[:2])
    v = vals[0]
    if has_any(t, ["duoi", "khong qua", "toi da", "max", "<", "it hon", "re hon", "do do"]):
        return None, v
    if has_any(t, ["tren", "hon", "it nhat", "toi thieu", ">", "tro len"]):
        return v, None
    if has_any(t, ["tam", "khoang", "~", "quanh"]):
        return int(v * 0.8), int(v * 1.2)
    return None, v  # "giày 2 triệu" → ngân sách tối đa


def parse_size(t: str):
    m = re.search(r"(?:size|sz|co|so|chan)\s*(\d{2}(?:[.,]5)?)", t)
    if m:
        return m.group(1).replace(",", ".")
    m = re.search(r"(?<![\d.,])(3[5-9]|4[0-7])(?![\d.,]|\s*(?:tr|k|trieu|cm))", t)
    return m.group(1) if m and has_any(t, ["giay", "doi", "mau", "con"]) else None


def parse_province(text: str):
    t = norm(text)
    for p in PROVINCES:
        if re.search(rf"(?<!\w){re.escape(norm(p))}(?!\w)", t):
            return p
    for alias, p in _PROVINCE_ALIASES.items():
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", t):
            return p
    return None


def parse_category(t: str):
    try:
        names = [c["name"] for c in backend.cached_get("/categories")]
    except backend.BackendError:
        names = []
    for n in names:
        if re.search(rf"(?<!\w){re.escape(norm(n))}(?!\w)", t):
            return n
    for alias in sorted(_CATEGORY_ALIASES, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", t):
            return _CATEGORY_ALIASES[alias]
    return None


def parse_brand(t: str):
    try:
        names = [b["name"] for b in backend.cached_get("/brands")]
    except backend.BackendError:
        names = []
    for n in names:
        if re.search(rf"(?<!\w){re.escape(norm(n))}(?!\w)", t):
            return n
    return None


def _keyword(text: str, used: list[str]) -> str | None:
    """Tên mẫu trong câu (vd 'air jordan 1', 'pegasus').

    Chỉ giữ các từ khách gõ KHÔNG dấu trong câu gốc (tên mẫu giày là tiếng Anh),
    bỏ từ dừng, tên thương hiệu/danh mục và các cụm giá/size.
    """
    low = text.lower()
    low = re.sub(r"(?:size|sz|cỡ|số)\s*\d{2}(?:[.,]5)?", " ", low)
    low = re.sub(r"\d+(?:[.,]\d+)?\s*(?:triệu|trieu|tr|củ|k|nghìn|ngàn|vnd|đồng|đ)\d?(?!\w)", " ", low)
    skip = {w for u in used if u for w in norm(u).split()}
    words = []
    for w in re.findall(r"[^\W_]+", low):
        if not w.isascii() or w in _STOPWORDS or w in skip:
            continue
        words.append(w)
    if not any(re.fullmatch(r"[a-z]{3,}", w) for w in words):
        return None
    return " ".join(words[:4])


def product_params(text: str) -> dict:
    t = norm(text)
    brand, category = parse_brand(t), parse_category(t)
    lo, hi = parse_price(t)
    size = parse_size(t)
    on_sale = has_any(t, ["sale", "giam gia", "dang giam", "khuyen mai", "xa kho"])
    sort = None
    if has_any(t, ["re nhat", "gia thap", "gia re"]):
        sort = "price_asc"
    elif has_any(t, ["dat nhat", "cao cap nhat", "xin nhat"]):
        sort = "price_desc"
    elif has_any(t, ["ban chay", "hot", "pho bien"]):
        sort = "best_selling"
    alias_hits = [a for a in _CATEGORY_ALIASES if re.search(rf"(?<!\w){re.escape(a)}(?!\w)", t)]
    kw = _keyword(text, [brand or "", category or "", *alias_hits])
    return {k: v for k, v in dict(brand=brand, category=category, size=size, min_price=lo, max_price=hi,
                                   on_sale=on_sale or None, sort=sort, keyword=kw).items() if v}


# ── Ý định ─────────────────────────────────────────────────────────────────────
_ORDER_CODE = re.compile(r"\bORD-?([A-Z0-9]{6,10})\b", re.I)

_INJECTION = ["ignore previous", "ignore all", "system prompt", "bo qua huong dan", "bo qua moi", "prompt cua ban",
              "jailbreak", "developer mode", "dong vai la", "you are now"]


def route_rules(text: str) -> Route | None:
    t = norm(text)
    if not t:
        return Route("greeting")
    if has_any(t, _INJECTION):
        return Route("refuse")
    if has_any(t, ["nhan vien", "tu van vien", "nguoi that", "gap admin", "chat voi nguoi", "cskh", "noi chuyen voi nguoi"]):
        return Route("handoff")

    m = _ORDER_CODE.search(text)
    if m:
        code = "ORD-" + m.group(1).upper()
        return Route("cancel_order" if has_any(t, ["huy"]) else "order_detail", {"code": code})
    if has_any(t, ["huy don", "huy dat", "khong muon mua nua"]):
        return Route("cancel_order")
    if has_any(t, ["don hang", "don cua", "don toi", "don minh", "kiem tra don", "theo doi don", "tinh trang don",
                   "don da dat", "da dat hang", "giao chua", "khi nao nhan", "bao gio nhan"]) \
            and not has_any(t, ["phi", "chinh sach", "lam sao de dat", "cach dat", "huong dan dat"]):
        return Route("my_orders")

    if has_any(t, ["phi ship", "phi van chuyen", "phi giao", "tien ship", "ship bao nhieu", "freeship", "free ship",
                   "mien phi van chuyen", "mien phi ship", "ship ve", "ship toi", "ship den", "giao ve", "giao den",
                   "giao mat bao lau", "giao bao lau", "bao lau thi nhan", "may ngay nhan", "bao nhieu ngay"]):
        return Route("shipping", {"province": parse_province(text)})

    productish = has_any(t, _PRODUCT_WORDS) or parse_brand(t) or parse_category(t)
    if has_any(t, ["ma giam", "voucher", "coupon", "ma khuyen mai", "ma uu dai", "uu dai gi", "khuyen mai gi",
                   "chuong trinh khuyen mai", "dang khuyen mai", "co giam gia khong"]) and not (
            productish and has_any(t, ["giay", "mau", "doi"])):
        return Route("vouchers")

    topic = None
    if has_any(t, ["doi tra", "tra hang", "hoan tien", "doi hang", "doi size", "tra lai", "hoan tra", "doi duoc", "duoc doi",
                   "doi lai", "doi sang", "doi mau", "doi co"]):
        topic = "return"
    elif has_any(t, ["bao hanh", "bi hong", "bong keo", "rach", "loi san xuat"]):
        topic = "warranty"
    elif has_any(t, ["thanh toan", "cod", "chuyen khoan", "vnpay", "tra gop", "the tin dung", "momo"]):
        topic = "payment"
    elif has_any(t, ["bang size", "chon size", "size nao", "cach do", "do chan", "chieu dai chan", "cm", "vua chan",
                     "rong chan", "chan be", "len size", "xuong size"]):
        topic = "size"
    elif has_any(t, ["bao mat", "du lieu ca nhan", "thong tin ca nhan", "xoa tai khoan"]):
        topic = "privacy"
    elif has_any(t, ["chinh hang", "chinh sach", "cam ket", "tich diem", "thanh vien", "cua hang o dau", "dia chi shop",
                     "gio mo cua", "lien he"]):
        topic = "general"
    if topic and not (topic == "size" and parse_brand(t) is None and has_any(t, ["con", "co size"])):
        return Route("policy", {"topic": topic})

    if productish:
        return Route("product_search", product_params(text))

    if has_any(t, ["cam on", "thanks", "thank", "tks", "ok cam on"]):
        return Route("thanks")
    if len(t) <= 25 and has_any(t, ["xin chao", "chao", "hello", "hi", "alo", "hey", "chao shop", "shop oi"]):
        return Route("greeting")
    return None


_ROUTER_PROMPT = """Bạn phân loại câu hỏi của khách cho chatbot cửa hàng giày PF. Shoes.
Trả về JSON đúng dạng: {"intent": "...", "topic": "...", "keyword": "..."}
intent là một trong:
- "product_search": khách hỏi/tìm/nhờ tư vấn sản phẩm giày
- "policy": hỏi về chính sách, cách mua hàng, đổi trả, bảo hành, thanh toán, size
- "general": chào hỏi, câu hỏi chung về cửa hàng
- "off_topic": không liên quan tới mua giày (thời tiết, bài tập, chính trị, viết code...)
topic (chỉ khi intent=policy): return | warranty | payment | shipping | size | privacy | general
keyword (chỉ khi intent=product_search): tên mẫu/nhu cầu ngắn gọn bằng tiếng Việt hoặc tên tiếng Anh, có thể rỗng."""


def route(text: str) -> Route:
    r = route_rules(text)
    if r:
        return r
    try:
        out = llm.complete_json(_ROUTER_PROMPT, text, max_tokens=60)
    except llm.LLMUnavailable:
        return Route("general", source="fallback")
    intent = out.get("intent")
    if intent == "product_search":
        params = product_params(text)
        kw = (out.get("keyword") or "").strip()
        if kw and "keyword" not in params and re.search(r"[A-Za-z]{3,}", kw):
            params["keyword"] = kw[:40]
        return Route("product_search", params, source="llm")
    if intent == "policy":
        topic = out.get("topic") if out.get("topic") in {"return", "warranty", "payment", "shipping", "size", "privacy", "general"} else "general"
        return Route("policy", {"topic": topic}, source="llm")
    if intent == "off_topic":
        return Route("off_topic", source="llm")
    return Route("general", source="llm")

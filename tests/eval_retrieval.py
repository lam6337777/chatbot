"""Đánh giá bước truy xuất của RAG (không gọi LLM sinh câu trả lời).

Mỗi câu hỏi được diễn đạt theo cách khách hay hỏi (khác chữ trong tài liệu) kèm các mục
tài liệu được coi là đúng. So sánh 3 cách tìm: keyword | semantic | hybrid.

Chỉ số:
- Hit@1: đoạn xếp đầu thuộc mục đúng
- Hit@3: có ít nhất 1 đoạn đúng trong 3 đoạn đưa cho LLM
- MRR  : trung bình 1/(thứ hạng của đoạn đúng đầu tiên)

Chạy (cần Ollama + bge-m3):  python -X utf8 tests/eval_retrieval.py [--verbose]
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)

from pf_bot import policies  # noqa: E402
from pf_bot.router import route_rules  # noqa: E402

# (câu hỏi, [các mục đúng — khớp theo chuỗi con của dòng tiêu đề đoạn])
CASES = [
    ("giày bị há mõm có được bảo hành không", ["Bảo hành bao gồm những lỗi gì", "ĐIỀU KIỆN BẢO HÀNH", "PHẠM VI BẢO HÀNH"]),
    ("mua về đi thấy chật muốn đổi cỡ khác", ["đổi size giày", "Điều kiện đổi trả", "Thời gian áp dụng", "ĐỔI TRẢ VÀ BẢO HÀNH"]),
    ("shop có lưu số thẻ ngân hàng của tôi không", ["BẢO MẬT THÔNG TIN THANH TOÁN", "NGUYÊN TẮC BẢO MẬT THANH TOÁN"]),
    ("đồ sale có trả lại được không", ["Sản phẩm giảm giá có được đổi trả", "Trường hợp không áp dụng"]),
    ("bao lâu thì tiền về lại tài khoản khi trả hàng", ["Hoàn tiền", "CHÍNH SÁCH HOÀN TIỀN", "hủy đơn hàng đã thanh toán"]),
    ("giày đi mòn đế thì có được bảo hành không", ["Trường hợp nào không được bảo hành", "ĐIỀU KIỆN BẢO HÀNH", "MỘT SỐ LƯU Ý"]),
    ("giày thể thao được bảo hành mấy tháng", ["THỜI HẠN BẢO HÀNH"]),
    ("gửi giày đi bảo hành mất mấy ngày mới nhận lại", ["Thời gian bảo hành mất bao lâu", "QUY TRÌNH BẢO HÀNH"]),
    ("nhà ở tỉnh xa thì gửi giày bảo hành kiểu gì", ["tỉnh xa", "QUY TRÌNH BẢO HÀNH"]),
    ("bảo hành có mất tiền không", ["PHÍ BẢO HÀNH"]),
    ("có xuất hóa đơn đỏ cho công ty không", ["hóa đơn VAT"]),
    ("trả bằng đô la được không", ["ngoại tệ"]),
    ("đã chuyển tiền rồi mà đơn chưa thấy xác nhận", ["đã chuyển khoản nhưng đơn hàng vẫn chưa được xác nhận", "XỬ LÝ GIAO DỊCH"]),
    ("bị trừ tiền hai lần thì xử lý sao", ["XỬ LÝ SAI SÓT TRONG THANH TOÁN"]),
    ("lúc shipper giao mà tôi đi vắng thì sao", ["không có nhà vào lúc giao hàng"]),
    ("có ship ra nước ngoài không", ["nước ngoài"]),
    ("nhận hàng thấy hộp bị móp thì làm gì", ["Trách nhiệm giao hàng", "VẬN CHUYỂN VÀ GIAO NHẬN"]),
    ("một đơn giao đến hai nơi được không", ["nhiều địa chỉ khác nhau"]),
    ("đặt xong rồi muốn sửa địa chỉ nhận", ["thay đổi thông tin đơn hàng"]),
    ("làm sao biết đúng cỡ chân của mình", ["chọn size giày phù hợp", "Cách đo chiều dài bàn chân", "Lưu ý khi chọn size", "Bảng quy đổi"]),
    ("chân bè thì nên lấy size thế nào", ["Lưu ý khi chọn size", "chọn size giày phù hợp"]),
    ("hàng hết thì bao giờ về lại", ["hết hàng, khi nào sẽ có lại"]),
    ("có cửa hàng để qua thử giày không", ["xem hàng trực tiếp"]),
    ("hàng có phải auth không hay fake", ["chính hãng"]),
    ("quên pass đăng nhập", ["quên mật khẩu"]),
    ("không muốn nhận mail quảng cáo nữa", ["hủy nhận email quảng cáo"]),
    ("tôi muốn xóa hẳn tài khoản", ["xóa tài khoản", "QUYỀN CỦA KHÁCH HÀNG"]),
    ("shop có tích điểm cho khách quen không", ["khách hàng thân thiết", "QUYỀN LỢI BẢO HÀNH ĐẶC BIỆT"]),
    ("muốn lấy sỉ giày về bán", ["đối tác bán buôn"]),
    ("shop có chia sẻ thông tin của tôi cho bên khác không", ["PHẠM VI CHIA SẺ THÔNG TIN", "Thông tin cá nhân của tôi có được bảo mật"]),
    ("web có dùng cookie theo dõi tôi không", ["COOKIE"]),
    ("đơn đã giao cho bên vận chuyển còn hủy được không", ["HỦY ĐƠN HÀNG", "thay đổi thông tin đơn hàng"]),
]

MODES = ["keyword", "semantic", "hybrid"]


def topic_for(q: str) -> str:
    r = route_rules(q)
    return r.params.get("topic", "general") if r and r.intent == "policy" else "general"


def evaluate(verbose=False):
    policies.warm_up()
    totals = {m: {"hit1": 0, "hit3": 0, "mrr": 0.0} for m in MODES}
    misses = {m: [] for m in MODES}
    for q, gold in CASES:
        topic = topic_for(q)
        for m in MODES:
            hits = policies.search(q, topic, k=10, mode=m)
            heads = [h["text"].split("\n", 1)[0] for h in hits]
            # Đoạn đúng: tiêu đề mục (hoặc nội dung, với tài liệu ngắn giữ nguyên) chứa mục kỳ vọng
            rank = next((i + 1 for i, h in enumerate(hits) if any(g.lower() in h["text"].lower() for g in gold)), None)
            if rank == 1:
                totals[m]["hit1"] += 1
            if rank and rank <= 3:
                totals[m]["hit3"] += 1
            totals[m]["mrr"] += 1 / rank if rank else 0
            if not rank or rank > 3:
                misses[m].append((q, heads[0]))
    n = len(CASES)
    print(f"{n} câu hỏi\n")
    print(f"{'Cách tìm':10} {'Hit@1':>7} {'Hit@3':>7} {'MRR':>7}")
    for m in MODES:
        t = totals[m]
        print(f"{m:10} {t['hit1'] / n:7.0%} {t['hit3'] / n:7.0%} {t['mrr'] / n:7.3f}")
    if verbose:
        for m in MODES:
            print(f"\n[{m}] trượt top-3 ({len(misses[m])}):")
            for q, top in misses[m]:
                print(f"  - {q}\n      → {top}")
    return totals


if __name__ == "__main__":
    evaluate("--verbose" in sys.argv)

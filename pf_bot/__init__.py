"""PF. Shoes chatbot core.

Luồng xử lý một câu hỏi:
    1. router.py   — nhận diện ý định + tách tham số bằng quy tắc (nhanh, chính xác);
                     chỉ gọi LLM khi câu hỏi không khớp quy tắc nào.
    2. tools.py    — lấy dữ liệu thật qua REST API của backend (sản phẩm, phí ship,
                     voucher, đơn hàng của chính khách qua JWT).
    3. bot.py      — câu trả lời dạng dữ liệu (ship, voucher, đơn) được dựng theo mẫu;
                     câu hỏi chính sách/chung được LLM trả lời dựa trên đoạn chính sách
                     liên quan (policies.py) và stream từng phần.
"""

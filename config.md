## 🏗️ Nguyên tắc Kiến trúc (Architecture Principles)

### 1. Reasoning-via-Action (Lập trình hóa Tư duy)
Hệ thống không hoạt động theo cách "đoán" câu trả lời bằng văn bản. Thay vào đó, AI được coi như một lập trình viên:
- **Nguyên tắc**: Tách biệt khả năng ngôn ngữ (LLM) và khả năng thực thi (Python REPL).
- **Hành động**: AI phải viết mã Python để trích xuất, tính toán và kiểm chứng dữ liệu từ Context hoặc Tools ngoại vi.
- **Dấu hiệu nhận biết**: Kết quả trả về chỉ được tin cậy khi đi qua lệnh `print()` trong môi trường Sandbox.

### 2. Stateless Execution & Recursion (Đệ quy & Cô lập)
Mỗi vòng lặp thực thi của Agent là độc lập:
- **Đệ quy**: Nếu dữ liệu đầu ra của một lần thực thi chưa đủ thỏa mãn yêu cầu, Agent tự gọi lại chính mình với phạm vi dữ liệu thu hẹp hơn.
- **Điểm dừng**: Agent phải xác định điểm dừng rõ ràng để tránh vòng lặp vô hạn.

### 3. Song song hóa (Parallel Orchestration)
Để giảm độ trễ (latency):
- **Guard & Classifier**: Hai tác vụ kiểm soát an ninh và phân loại ý định phải được chạy song song ngay khi nhận request từ người dùng.

---


## 🛠️ Quy chuẩn Lập trình (Coding Standards)

### 1. Quy trình thực thi trong REPL
AI khi viết code Python phải tuân thủ:
- **Trích xuất dữ liệu**: Luôn sử dụng hàm `print()` để đưa kết quả ra ngoài.
- **Tiết kiệm Token**: Sử dụng `get_slice()` hoặc `search()` để đọc các phần cần thiết của Context khổng lồ thay vì nạp toàn bộ.

### 2. Quy chuẩn đặt tên (Naming Conventions)
- **Files**: `Snake_case` (Ví dụ: `product_agent.py`, `price_tools.py`).
- **Agents**: Đặt tên theo đúng chức năng nghiệp vụ quy định trong 8 nhóm chính.
- **Tools**: Phải có tiền tố gợi nhớ đến module (Ví dụ: `get_product`, `fetch_price`).

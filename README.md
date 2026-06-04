# PF Chatbot - Hệ thống Chatbot thông minh với RLM Engine

Dự án này là một chatbot chuyên dụng cho cửa hàng giày PF, sử dụng kiến trúc RLM (Recursive Language Model) Engine để xử lý lý luận và cung cấp câu trả lời chính xác dựa trên dữ liệu thực tế từ cơ sở dữ liệu.

## Yêu cầu hệ thống

- **Phiên bản Python:** Python 3.10 trở lên.
- **Cơ sở dữ liệu:** PostgreSQL (để lưu trữ thông tin sản phẩm, đơn hàng, v.v.).

## Hướng dẫn cài đặt

1. **Clone dự án hoặc tải mã nguồn về máy.**

2. **Tạo môi trường ảo (Khuyên dùng):**
   ```bash
   python -m venv venv
   ```

3. **Kích hoạt môi trường ảo:**
   - Trên Windows:
     ```bash
     .\venv\Scripts\activate
     ```
   - Trên Linux/macOS:
     ```bash
     source venv/bin/activate
     ```

4. **Cài đặt các thư viện cần thiết:**
   ```bash
   pip install -r requirements.txt
   ```

## Cấu hình môi trường

Tạo file `.env` trong thư mục gốc của dự án (dựa trên file `.env` mẫu) với các thông tin sau:

```env
# OpenAI / LLM API Configuration
API_KEY=your_api_key_here
MODEL_Flash=gpt-3.5-turbo  # Hoặc model bạn muốn sử dụng

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=shoe_store
DB_USER=postgres
DB_PASSWORD=your_password_here
```

## Cách chạy ứng dụng

Để khởi chạy chatbot, thực hiện lệnh sau:

```bash
python main.py
```

Sau khi chạy, bạn có thể tương tác trực tiếp với chatbot thông qua cửa sổ terminal. Gõ `exit` hoặc `quit` để thoát.

## Cấu trúc thư mục chính

- `main.py`: File thực thi chính của hệ thống.
- `Agents/`: Chứa các agent xử lý logic chuyên biệt (Sản phẩm, Đơn hàng, v.v.).
- `MCP_Tools/`: Chứa các công cụ kết nối với Database và thực hiện hành động.
- `rlm_engine.py`: Engine xử lý lý luận sau khi có dữ liệu thô.
- `llm_client.py`: Client kết nối với API ngôn ngữ lớn.
- `db_client.py`: Quản lý kết nối cơ sở dữ liệu PostgreSQL.

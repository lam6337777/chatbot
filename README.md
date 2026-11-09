---
title: PF Shoes Chatbot
emoji: 👟
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

<!-- Phần trên là cấu hình cho Hugging Face Spaces (Docker), GitHub hiển thị dạng bảng nhỏ. -->

# PF. Shoes chatbot

Trợ lý mua sắm cho storefront: tìm giày, báo phí ship, mã giảm giá, tra cứu đơn hàng của chính khách và giải đáp chính sách. Chạy bằng FastAPI ở cổng **8000**, dùng mô hình AI chạy local qua [Ollama](https://ollama.com) (mặc định `qwen2.5:3b`).

## Chạy

Cần backend (`API-DATN`, cổng 8082) và PostgreSQL đang chạy; Ollama phải đang chạy nền (trên Windows Ollama tự khởi động cùng máy).

```bash
ollama pull qwen2.5:3b            # lần đầu, ~1.9 GB — model trả lời
ollama pull bge-m3                # lần đầu, ~1.2 GB — model embedding cho RAG
python -m venv venv
venv\Scripts\activate             # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
python app.py                     # http://localhost:8000/api/health
```

`start-all.bat` ở thư mục gốc làm sẵn các bước trên (trừ `ollama pull`).

## Cấu hình — `.env`

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `USE_OLLAMA` | `true` | `true`: dùng Ollama local; `false`: dùng endpoint tương thích OpenAI bên dưới |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Model Ollama |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | DeepSeek | Chỉ dùng khi `USE_OLLAMA=false` (vd `https://api.deepseek.com`, `deepseek-chat`) |
| `LLM_MAX_TOKENS` / `LLM_TEMPERATURE` | `512` / `0.3` | |
| `EMBED_MODEL` / `EMBED_BASE_URL` | `bge-m3` / Ollama | Model embedding cho RAG |
| `DB_HOST` `DB_PORT` `DB_NAME` `DB_USER` `DB_PASSWORD` | | PostgreSQL — chỉ dùng để lưu lịch sử chat AI |
| `BACKEND_API_URL` | `http://localhost:8082/api` | REST API của backend |
| `CHATBOT_ALLOWED_ORIGINS` | `http://localhost:3000` | CORS, phân tách bằng dấu phẩy |
| `CHATBOT_PORT` | `8000` | |

**Chọn model:** máy có GPU 4 GB VRAM nên dùng model ≤ 3B để chạy hoàn toàn trên GPU (`qwen2.5:3b` ≈ 3–4 giây/câu hỏi chính sách). Model 7B trở lên sẽ chạy một phần trên CPU và chậm hơn nhiều.

## Cách hoạt động

```
câu hỏi ─► router.py ──► ý định + tham số (quy tắc tiếng Việt; chỉ hỏi LLM khi không khớp)
              │
              ├─ product_search ─► GET /api/products  ─► lời dẫn + thẻ sản phẩm
              ├─ shipping       ─► GET /api/shipping/quote
              ├─ vouchers       ─► GET /api/vouchers/available          (trả lời theo mẫu,
              ├─ my_orders / order_detail / cancel_order                  không qua LLM)
              │                 ─► GET /api/orders… bằng JWT của khách
              ├─ policy         ─► RAG: policies.py tìm đoạn chính sách liên quan ─► LLM trả lời (stream)
              └─ general        ─► LLM + đoạn FAQ
```

- **Dữ liệu luôn lấy qua API backend**, không truy vấn thẳng bảng sản phẩm/đơn hàng — giá, phí ship, quyền xem đơn do backend quyết định.
- **Đơn hàng**: chatbot gọi backend bằng JWT của khách, nên chỉ thấy đơn của chính khách. Bot không tự hủy đơn; nó gửi link tới trang đơn để khách bấm “Hủy đơn hàng” (backend hoàn tồn kho + voucher).
- **Câu có đáp án cố định** (phí ship, voucher, đơn hàng, đổi cm → size, hình thức thanh toán) được dựng theo mẫu từ dữ liệu thật — trả lời tức thì và không thể “bịa”.
- **Chính sách (RAG)**: xem mục dưới.

## RAG cho tài liệu chính sách

1. **Chia đoạn** — mỗi tài liệu trong `Data_policy/` được chia theo tiêu đề mục (~550 ký tự/đoạn); tài liệu ngắn (< 1.500 ký tự) giữ nguyên một đoạn. Mỗi đoạn có tiền tố `[Tên tài liệu — Tên mục]` để tự đủ nghĩa. Số điện thoại/link giữ chỗ (`1900 xxxx`, `[X] VNĐ`) được thay trước khi nạp.
2. **Embedding** — các đoạn được mã hóa bằng `bge-m3` (Ollama, 1024 chiều) một lần và cache ở `.cache/policy_embeddings.json`; tự tính lại khi tài liệu đổi. Server nạp sẵn khi khởi động.
3. **Truy xuất hybrid** — `0.9 × cosine(câu hỏi, đoạn) + 0.1 × điểm từ khóa + 0.05 nếu đúng chủ đề router đoán`; lấy 3 đoạn tốt nhất (~60 ms/câu hỏi).
4. **Sinh câu trả lời** — LLM chỉ được dùng các đoạn này, phải nêu rõ điều kiện/ngoại lệ, không bịa số liệu.

Không gọi được model embedding → tự quay về tìm theo từ khóa, chatbot vẫn chạy.

**Đánh giá** (`python -X utf8 tests/eval_retrieval.py --verbose`) trên 32 câu hỏi được diễn đạt khác chữ trong tài liệu (vd “giày bị há mõm có được bảo hành không”, “trả bằng đô la được không”):

| Cách tìm | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| Từ khóa (trước đây) | 62% | 84% | 0.732 |
| Theo nghĩa (bge-m3) | 88% | 97% | 0.922 |
| **Hybrid (đang dùng)** | **91%** | **97%** | **0.938** |

## API

Mọi request gửi `Authorization: Bearer <JWT storefront>`; chatbot hỏi backend `/api/users/me` để biết người dùng (không tin `userid` do client gửi). Khách chưa đăng nhập vẫn hỏi được nhưng không lưu lịch sử và không tra được đơn.

| Method | Path | |
|---|---|---|
| GET | `/api/health` | Trạng thái + model đang dùng |
| POST | `/api/chat/stream` | `{message, session_id?}` → SSE: `session`, `meta`, `delta`, `products`, `handoff`, `done` |
| GET | `/api/chat/sessions` | Phiên chat của người dùng hiện tại |
| POST | `/api/chat/session` | Tạo phiên |
| GET | `/api/chat/session/{id}/messages` | Tin nhắn (kèm thẻ sản phẩm đã lưu) |
| PATCH | `/api/chat/session/{id}` | Đổi tên `{title}` |
| DELETE | `/api/chat/session/{id}` | Xóa phiên |

Lịch sử lưu ở bảng `ai_chat_sessions` / `ai_chat_messages` (PostgreSQL `shoe`). Giới hạn: 500 ký tự/câu, 20 câu/phút/người.

## Cấu trúc

```
app.py              FastAPI: xác thực, phiên chat, SSE
pf_bot/
  router.py         nhận diện ý định, tách hãng/danh mục/size/giá/tỉnh
  tools.py          gọi REST API backend
  bot.py            điều phối + mẫu câu trả lời + persona LLM
  policies.py       RAG: chia đoạn, embedding, truy xuất hybrid
  llm.py            client OpenAI-compatible (Ollama/cloud)
  sessions.py       lưu lịch sử chat AI
  backend.py text.py config.py
Data_policy/        tài liệu chính sách
tests/              test_router.py (không cần LLM), eval_retrieval.py (đánh giá RAG), test_bot.py (cần backend + Ollama)
legacy/             code chatbot cũ, không còn dùng
```

Kiểm tra nhanh bộ định tuyến: `python -X utf8 tests/test_router.py`.

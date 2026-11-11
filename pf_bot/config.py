import os

from dotenv import load_dotenv

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"))

ROOT_DIR = _ROOT
POLICY_DIR = os.path.join(_ROOT, "Data_policy")

# REST API của backend Spring Boot (nguồn dữ liệu duy nhất cho sản phẩm/đơn hàng/ship/voucher)
BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "http://localhost:8082/api").rstrip("/")

# ── Nhà cung cấp AI ────────────────────────────────────────────────────────────
#   ollama : chạy local (mặc định khi phát triển)
#   gemini : Google Gemini API (gói miễn phí) — dùng khi deploy
#   openai : endpoint tương thích OpenAI bất kỳ (DeepSeek, Groq, OpenAI…)
_legacy = "ollama" if os.environ.get("USE_OLLAMA", "true").lower() == "true" else "openai"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", _legacy).lower()

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")

if LLM_PROVIDER == "gemini":
    LLM_BASE_URL = GEMINI_BASE_URL
    LLM_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    LLM_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    EMBED_BASE_URL = GEMINI_BASE_URL
    EMBED_API_KEY = LLM_API_KEY
    EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001")
elif LLM_PROVIDER in ("deepseek", "openai"):
    _ds = LLM_PROVIDER == "deepseek"
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_API_KEY = os.environ.get("DEEPSEEK_API_KEY" if _ds else "LLM_API_KEY", "") or os.environ.get("LLM_API_KEY", "")
    LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
    # DeepSeek không có API embedding → RAG dùng Gemini nếu có GEMINI_API_KEY, ngược lại dùng Ollama
    _gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if "EMBED_BASE_URL" not in os.environ and _gemini_key:
        EMBED_BASE_URL = GEMINI_BASE_URL
        EMBED_API_KEY = _gemini_key
        EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001")
    else:
        EMBED_BASE_URL = os.environ.get("EMBED_BASE_URL", OLLAMA_BASE_URL)
        EMBED_API_KEY = os.environ.get("EMBED_API_KEY", "ollama")
        EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
else:
    LLM_PROVIDER = "ollama"
    LLM_BASE_URL = OLLAMA_BASE_URL
    LLM_API_KEY = "ollama"
    LLM_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
    EMBED_BASE_URL = os.environ.get("EMBED_BASE_URL", OLLAMA_BASE_URL)
    EMBED_API_KEY = "ollama"
    EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")

LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", 512))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", 0.3))

# Số tin nhắn gần nhất đưa vào ngữ cảnh khi trả lời: 6 tin = 3 lượt hỏi–đáp gần nhất
HISTORY_TURNS = 6

# ── Database (chỉ dùng để lưu lịch sử chat AI) ──────────────────────────────────
# Ưu tiên DATABASE_URL (chuỗi kết nối Neon/Supabase: postgresql://user:pass@host/db?sslmode=require)
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DB = dict(
    host=os.environ.get("DB_HOST", "localhost"),
    port=os.environ.get("DB_PORT", "5432"),
    dbname=os.environ.get("DB_NAME", "shoe"),
    user=os.environ.get("DB_USER", "postgres"),
    password=os.environ.get("DB_PASSWORD", ""),
)

# Origin của storefront được phép gọi chatbot (CORS), phân tách bằng dấu phẩy
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("CHATBOT_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

# Server: Hugging Face Spaces yêu cầu lắng nghe 0.0.0.0:7860
HOST = os.environ.get("CHATBOT_HOST", "127.0.0.1")
PORT = int(os.environ.get("CHATBOT_PORT", os.environ.get("PORT", 8000)))

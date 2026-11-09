"""PF. Shoes chatbot API (FastAPI, cổng 8000).

Xác thực: widget gửi JWT của storefront qua header `Authorization: Bearer <token>`;
chatbot hỏi backend `/api/users/me` để biết người dùng — không tin `userid` từ client.
"""
import json
import logging
import time
from collections import defaultdict, deque

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import threading

from pf_bot import backend, bot, llm, policies, sessions
from pf_bot.config import ALLOWED_ORIGINS, HISTORY_TURNS, HOST, PORT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("pf_bot.api")

app = FastAPI(title="PF Shoes Chatbot API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Auth ───────────────────────────────────────────────────────────────────────
def _token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def optional_user(authorization: str | None = Header(default=None)):
    jwt = _token(authorization)
    user = backend.current_user(jwt)
    return (user, jwt if user else None)


def require_user(auth=Depends(optional_user)):
    user, _ = auth
    if not user:
        raise HTTPException(401, "Anh/chị vui lòng đăng nhập")
    return user


def _own_session(session_id: int, user: dict):
    if not sessions.owns(session_id, user["id"]):
        raise HTTPException(404, "Không tìm thấy cuộc trò chuyện")


# ── Giới hạn tần suất đơn giản (mỗi người/IP tối đa 20 câu/phút) ────────────────
_hits: dict[str, deque] = defaultdict(deque)


def _rate_limit(key: str, limit=20, window=60):
    now = time.time()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Dạ, anh/chị gửi hơi nhanh, vui lòng đợi một chút rồi thử lại ạ")
    q.append(now)


# ── Phiên chat ─────────────────────────────────────────────────────────────────
class NewSession(BaseModel):
    title: str = Field(default="Cuộc trò chuyện mới", max_length=120)


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class Ask(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    session_id: int | None = None


@app.on_event("startup")
def _startup():
    try:
        sessions.init_schema()
    except Exception:
        log.exception("Không khởi tạo được bảng lịch sử chat")
    _warm_rag()


def _warm_rag():
    # Nạp tài liệu + embedding ở nền để khách đầu tiên không phải chờ
    threading.Thread(target=policies.warm_up, daemon=True).start()


@app.get("/api/health")
def health():
    return {"status": "ok", "llm": llm.describe(), "rag": policies.status()}


@app.get("/api/chat/sessions")
def list_sessions(user=Depends(require_user)):
    return {"sessions": sessions.list_sessions(user["id"])}


@app.post("/api/chat/session")
def create_session(body: NewSession, user=Depends(require_user)):
    return sessions.create_session(user["id"], body.title)


@app.get("/api/chat/session/{session_id}/messages")
def session_messages(session_id: int, user=Depends(require_user)):
    _own_session(session_id, user)
    out = []
    for m in sessions.messages(session_id):
        content, extra = sessions.split_extra(m["content"])
        out.append({"id": m["id"], "role": m["role"], "content": content, "created_at": m["created_at"],
                    "products": (extra or {}).get("products"), "handoff": bool((extra or {}).get("handoff"))})
    return {"messages": out}


@app.patch("/api/chat/session/{session_id}")
def rename_session(session_id: int, body: Rename, user=Depends(require_user)):
    _own_session(session_id, user)
    sessions.rename(session_id, body.title)
    return {"ok": True}


@app.delete("/api/chat/session/{session_id}")
def delete_session(session_id: int, user=Depends(require_user)):
    _own_session(session_id, user)
    sessions.delete(session_id)
    _state.pop(session_id, None)
    return {"ok": True}


# Trạng thái hội thoại ngắn hạn (bộ lọc sản phẩm lượt trước) theo phiên
_state: dict = defaultdict(dict)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.post("/api/chat/stream")
def chat_stream(body: Ask, auth=Depends(optional_user), x_forwarded_for: str | None = Header(default=None)):
    user, jwt = auth
    _rate_limit(f"u{user['id']}" if user else f"ip{x_forwarded_for or 'local'}")
    question = body.message.strip()

    session_id = body.session_id
    history: list[dict] = []
    if user:
        if session_id:
            _own_session(session_id, user)
            history = sessions.recent_history(session_id, HISTORY_TURNS)
        else:
            session_id = sessions.create_session(user["id"], question[:60])["id"]
        sessions.add_message(session_id, "user", question)
    # Khách chưa đăng nhập không có phiên → không giữ trạng thái giữa các câu (tránh lẫn giữa các khách)
    state = _state[session_id] if session_id else {}

    def gen():
        if user and not body.session_id:
            yield _sse({"type": "session", "id": session_id, "title": question[:60]})
        text, products, handoff, intent = [], None, False, None
        saved = False

        def save():
            nonlocal saved
            answer = "".join(text).strip()
            if saved or not user or not answer:
                return None
            saved = True
            extra = {k: v for k, v in {"products": products, "handoff": handoff}.items() if v}
            return sessions.add_message(session_id, "bot", answer, intent, extra or None)

        try:
            for ev in bot.respond(question, history, jwt, state):
                if ev["type"] == "delta":
                    text.append(ev["text"])
                elif ev["type"] == "products":
                    products = ev["items"]
                elif ev["type"] == "handoff":
                    handoff = True
                elif ev["type"] == "meta":
                    intent = ev["intent"]
                yield _sse(ev)
        except GeneratorExit:
            # Khách đóng widget/chuyển phiên giữa chừng: vẫn lưu phần đã trả lời
            save()
            raise
        except Exception:
            log.exception("chat failed")
            msg = "Dạ, em xin lỗi, hệ thống đang gặp sự cố ạ. Anh/chị vui lòng thử lại sau hoặc chat với nhân viên giúp em nhé."
            text.append(msg)
            yield _sse({"type": "delta", "text": msg})
        yield _sse({"type": "done", "message_id": save()})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    log.info("LLM: %s", llm.describe())
    uvicorn.run(app, host=HOST, port=PORT)

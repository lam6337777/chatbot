"""Lưu phiên chat AI vào 2 bảng có sẵn: ai_chat_sessions, ai_chat_messages."""
import json

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from .config import DATABASE_URL, DB

# Neon/Supabase cung cấp DATABASE_URL (có sslmode=require); local dùng các biến DB_* riêng lẻ
_pool = pool.SimpleConnectionPool(1, 5, dsn=DATABASE_URL) if DATABASE_URL else pool.SimpleConnectionPool(1, 5, **DB)


class _Conn:
    def __enter__(self):
        self.conn = _pool.getconn()
        return self.conn.cursor(cursor_factory=RealDictCursor)

    def __exit__(self, exc_type, *_):
        try:
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
        finally:
            _pool.putconn(self.conn)


def init_schema():
    """Tạo 2 bảng lịch sử chat nếu database mới chưa có (database cũ đã có sẵn → bỏ qua)."""
    with _Conn() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ai_chat_sessions (
                id BIGSERIAL PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                title VARCHAR(255),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_ai_session_user ON ai_chat_sessions (user_id, updated_at DESC);
            CREATE TABLE IF NOT EXISTS ai_chat_messages (
                id BIGSERIAL PRIMARY KEY,
                session_id BIGINT NOT NULL,
                role VARCHAR(16) NOT NULL,
                content TEXT NOT NULL,
                intent VARCHAR(64),
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_ai_msg_session ON ai_chat_messages (session_id, created_at);
        """)


def _iso(row):
    for k in ("created_at", "updated_at"):
        if row.get(k) is not None:
            row[k] = row[k].isoformat()
    return row


def list_sessions(user_id: int, limit=30):
    with _Conn() as cur:
        cur.execute("SELECT id, title, created_at, updated_at FROM ai_chat_sessions WHERE user_id = %s "
                    "ORDER BY updated_at DESC LIMIT %s", (str(user_id), limit))
        return [_iso(r) for r in cur.fetchall()]


def create_session(user_id: int, title: str):
    with _Conn() as cur:
        cur.execute("INSERT INTO ai_chat_sessions (user_id, title, created_at, updated_at) VALUES (%s, %s, NOW(), NOW()) "
                    "RETURNING id, title, created_at, updated_at", (str(user_id), title[:120]))
        return _iso(cur.fetchone())


def owns(session_id: int, user_id: int) -> bool:
    with _Conn() as cur:
        cur.execute("SELECT 1 FROM ai_chat_sessions WHERE id = %s AND user_id = %s", (session_id, str(user_id)))
        return cur.fetchone() is not None


def messages(session_id: int, limit=200):
    with _Conn() as cur:
        cur.execute("SELECT id, role, content, intent, created_at FROM ai_chat_messages WHERE session_id = %s "
                    "ORDER BY created_at, id LIMIT %s", (session_id, limit))
        return [_iso(r) for r in cur.fetchall()]


def recent_history(session_id: int, n: int):
    with _Conn() as cur:
        cur.execute("SELECT role, content FROM ai_chat_messages WHERE session_id = %s ORDER BY created_at DESC, id DESC LIMIT %s",
                    (session_id, n))
        return list(reversed(cur.fetchall()))


def add_message(session_id: int, role: str, content: str, intent: str | None = None, extra: dict | None = None):
    # Thẻ sản phẩm được lưu kèm (JSON ở cuối nội dung) để mở lại phiên vẫn thấy
    stored = content if not extra else f"{content}\n<!--pf:{json.dumps(extra, ensure_ascii=False)}-->"
    with _Conn() as cur:
        cur.execute("INSERT INTO ai_chat_messages (session_id, role, content, intent, created_at) VALUES (%s, %s, %s, %s, NOW()) "
                    "RETURNING id", (session_id, role, stored, intent))
        mid = cur.fetchone()["id"]
        cur.execute("UPDATE ai_chat_sessions SET updated_at = NOW() WHERE id = %s", (session_id,))
        return mid


def rename(session_id: int, title: str):
    with _Conn() as cur:
        cur.execute("UPDATE ai_chat_sessions SET title = %s, updated_at = NOW() WHERE id = %s", (title[:120], session_id))


def delete(session_id: int):
    with _Conn() as cur:
        cur.execute("DELETE FROM ai_chat_messages WHERE session_id = %s", (session_id,))
        cur.execute("DELETE FROM ai_chat_sessions WHERE id = %s", (session_id,))


def split_extra(content: str):
    """Tách phần JSON đính kèm (thẻ sản phẩm) khỏi nội dung đã lưu."""
    marker = "\n<!--pf:"
    if marker in content and content.endswith("-->"):
        body, raw = content.rsplit(marker, 1)
        try:
            return body, json.loads(raw[:-3])
        except json.JSONDecodeError:
            pass
    return content, None

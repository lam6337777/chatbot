"""Tài liệu chính sách + RAG (Retrieval-Augmented Generation).

Mỗi tài liệu trong Data_policy/ được chia thành đoạn ngắn (kèm tên tài liệu + tiêu đề mục để
đoạn tự đủ nghĩa). Khi có câu hỏi, điểm của mỗi đoạn là kết hợp (hybrid):

    0.90 × độ gần nghĩa (cosine giữa embedding câu hỏi và embedding đoạn, model bge-m3)
  + 0.10 × điểm từ khóa (từ đơn + cặp từ trùng, đã chuẩn hóa về 0..1)
  + 0.05 nếu đoạn thuộc tài liệu đúng chủ đề router đoán

Trọng số chọn bằng tests/eval_retrieval.py (32 câu hỏi diễn đạt khác tài liệu):
    keyword  Hit@1 62%  Hit@3 84%  MRR 0.732
    semantic Hit@1 88%  Hit@3 97%  MRR 0.922
    hybrid   Hit@1 91%  Hit@3 97%  MRR 0.938

Embedding các đoạn được tính một lần và lưu ở .cache/policy_embeddings.json; tự tính lại khi
nội dung tài liệu hoặc model thay đổi. Nếu không gọi được model embedding (Ollama tắt / chưa
pull model) thì tự quay về chỉ dùng điểm từ khóa — chatbot vẫn trả lời được.
"""
import hashlib
import json
import logging
import math
import os
import re
from collections import Counter

from openai import OpenAI

from .config import EMBED_API_KEY, EMBED_BASE_URL, EMBED_MODEL, POLICY_DIR, ROOT_DIR
from .text import norm

log = logging.getLogger("pf_bot.rag")

DOC_TITLES = {
    "return_refund_policy.txt.txt": "Chính sách đổi trả & hoàn tiền",
    "warranty_policy.txt.txt": "Chính sách bảo hành",
    "payment_policy.txt.txt": "Chính sách thanh toán",
    "shipping_policy.txt.txt": "Chính sách vận chuyển",
    "size_guild.txt.txt": "Hướng dẫn chọn size",
    "privacy_policy.txt.txt": "Chính sách bảo mật",
    "sales_policy.txt.txt": "Chính sách bán hàng",
    "faq.txt.txt": "Câu hỏi thường gặp",
}

# Tài liệu chính của từng chủ đề (router trả về topic) — chỉ dùng để cộng điểm nhẹ
TOPIC_FILES = {
    "return": ["return_refund_policy.txt.txt", "faq.txt.txt"],
    "warranty": ["warranty_policy.txt.txt"],
    "payment": ["payment_policy.txt.txt"],
    "shipping": ["shipping_policy.txt.txt"],
    "size": ["size_guild.txt.txt"],
    "privacy": ["privacy_policy.txt.txt"],
    "sales": ["sales_policy.txt.txt"],
    "general": ["faq.txt.txt", "sales_policy.txt.txt"],
}

W_SEMANTIC, W_KEYWORD, W_TOPIC = 0.90, 0.10, 0.05
CHUNK_CHARS = 550
WHOLE_DOC_CHARS = 1500  # tài liệu ngắn hơn mức này giữ nguyên 1 đoạn (câu hỏi chung cần cả tài liệu)

# Thay các chỗ giữ chỗ trong tài liệu gốc để bot không đọc ra thông tin giả
_REPLACEMENTS = [
    (re.compile(r"(?:Hotline|hotline|số)\s*1900\s*x+", re.I), "mục Chat với nhân viên trên website"),
    (re.compile(r"1900\s*x+", re.I), "mục Chat với nhân viên trên website"),
    (re.compile(r"\[X\]\s*VNĐ"), "1.000.000đ"),
]
_STOP = set("la co khong the nao gi va cua cho toi minh ban em anh chi shop thi ma voi duoc nhu bao nhieu o tai trong mot cac nhung".split())
_HEADING = re.compile(r"^\**\s*(?:[A-Z]\.|\d+(?:\.\d+)*\.)?\s*[A-ZÀ-Ỹ0-9][^\n]{2,80}?\**$")

_chunks: list[dict] | None = None
_embed_ok: bool | None = None  # None = chưa thử
_client = OpenAI(api_key=EMBED_API_KEY or "none", base_url=EMBED_BASE_URL, timeout=30, max_retries=1)
_CACHE = os.path.join(ROOT_DIR, ".cache", "policy_embeddings.json")


# ── Chia đoạn ──────────────────────────────────────────────────────────────────
def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for pattern, repl in _REPLACEMENTS:
        text = pattern.sub(repl, text)
    return text


def _tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"\w+", norm(s)) if t not in _STOP and len(t) > 1]


_NUMBERED = re.compile(r"^\**\s*(?:[A-Z]\.|\d+(?:\.\d+)*\.)\s+(.{2,90}?)\**\s*:?$")


def _heading_text(line: str) -> str | None:
    """Dòng tiêu đề mục: '3. PHƯƠNG THỨC…', '**2. THỜI HẠN BẢO HÀNH**', 'A. CÂU HỎI…', hoặc dòng in hoa ngắn.
    Trả về tiêu đề đã bỏ số thứ tự (để model không trả lời kiểu "xem mục 4")."""
    s = line.strip()
    if not s or len(s) > 100 or s.startswith(("-", "*  ", "|")):
        return None
    m = _NUMBERED.match(s)
    if m:
        return m.group(1).strip("* ")
    bare = s.strip("* ")
    if len(bare) >= 4 and bare.upper() == bare and re.search(r"[A-ZÀ-Ỹ]{3}", bare):
        return bare
    return None


def _make(fname: str, text: str) -> dict:
    toks = _tokens(text)
    return {"file": fname, "text": text, "tokens": Counter(toks), "bigrams": Counter(zip(toks, toks[1:]))}


def _split(fname: str, raw: str) -> list[dict]:
    """Chia theo tiêu đề mục; mục dài được tách tiếp ở ranh giới dòng (~CHUNK_CHARS ký tự)."""
    title = DOC_TITLES.get(fname, fname)
    if len(raw) <= WHOLE_DOC_CHARS:
        lines = []
        for line in raw.split("\n"):
            head = _heading_text(line)
            lines.append(f"**{head}**" if head else line)
        body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
        return [_make(fname, f"[{title}]\n{body}")]
    out, buf, section = [], "", ""
    for line in raw.split("\n"):
        if line.strip() == "---":
            continue
        head = _heading_text(line)
        if head:
            if buf.strip():
                out.append((section, buf.strip()))
            buf, section = "", head
            continue
        # Mục dài: cắt ở dòng trống hoặc đầu một gạch đầu dòng/câu hỏi mới
        starts_item = not line.strip() or line.lstrip().startswith(("- ", "**H:", "**"))
        if len(buf) > CHUNK_CHARS and starts_item and buf.strip():
            out.append((section, buf.strip()))
            buf = ""
        buf += line + "\n"
    if buf.strip():
        out.append((section, buf.strip()))
    out = [(s, re.sub(r"\n{3,}", "\n\n", b)) for s, b in out]

    chunks = []
    for sec, body in out:
        # Tiền tố ngữ cảnh giúp đoạn ngắn vẫn đủ nghĩa khi tìm theo vector
        header = f"[{title}{' — ' + sec if sec and sec.lower() != title.lower() else ''}]"
        chunks.append(_make(fname, f"{header}\n{body}"))
    return chunks


def _load():
    global _chunks
    _chunks = []
    for fname in sorted(os.listdir(POLICY_DIR)):
        with open(os.path.join(POLICY_DIR, fname), encoding="utf-8") as f:
            _chunks.extend(_split(fname, _clean(f.read())))
    log.info("Đã nạp %d đoạn chính sách", len(_chunks))


# ── Embedding ──────────────────────────────────────────────────────────────────
def _normalize(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _embed(texts: list[str]) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), 32):
        resp = _client.embeddings.create(model=EMBED_MODEL, input=texts[i:i + 32])
        out.extend(_normalize(d.embedding) for d in resp.data)
    return out


def _ensure_embeddings() -> bool:
    """Gắn vector cho mọi đoạn (từ cache hoặc tính mới). Trả False nếu không dùng được embedding."""
    global _embed_ok
    if _embed_ok is not None:
        return _embed_ok
    fingerprint = hashlib.sha256((EMBED_MODEL + "".join(c["text"] for c in _chunks)).encode()).hexdigest()
    try:
        with open(_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
        if cache.get("fingerprint") == fingerprint:
            for c, v in zip(_chunks, cache["vectors"]):
                c["vec"] = v
            _embed_ok = True
            log.info("RAG: dùng embedding đã cache (%d đoạn, model %s)", len(_chunks), EMBED_MODEL)
            return True
    except (OSError, ValueError, KeyError):
        pass
    try:
        vectors = _embed([c["text"] for c in _chunks])
    except Exception as e:
        log.warning("RAG: không tạo được embedding (%s) — chỉ tìm theo từ khóa", e)
        _embed_ok = False
        return False
    for c, v in zip(_chunks, vectors):
        c["vec"] = v
    os.makedirs(os.path.dirname(_CACHE), exist_ok=True)
    with open(_CACHE, "w", encoding="utf-8") as f:
        json.dump({"fingerprint": fingerprint, "model": EMBED_MODEL, "vectors": vectors}, f)
    _embed_ok = True
    log.info("RAG: đã tạo embedding cho %d đoạn (model %s)", len(_chunks), EMBED_MODEL)
    return True


def status() -> dict:
    return {"chunks": len(_chunks or []), "embedding_model": EMBED_MODEL,
            "mode": "hybrid" if _embed_ok else ("keyword" if _embed_ok is False else "loading")}


def warm_up():
    """Gọi lúc khởi động server để không bắt khách đầu tiên chờ tạo embedding."""
    if _chunks is None:
        _load()
    _ensure_embeddings()


# ── Tìm kiếm ───────────────────────────────────────────────────────────────────
def _keyword_scores(query: str) -> list[float]:
    q = _tokens(query)
    qset, qb = set(q), set(zip(q, q[1:]))
    return [sum(1 for t in qset if t in c["tokens"]) + 2 * sum(1 for b in qb if b in c["bigrams"]) for c in _chunks]


def search(query: str, topic: str = "general", k: int = 3, mode: str = "hybrid") -> list[dict]:
    """Trả về k đoạn tốt nhất kèm điểm. mode: hybrid | semantic | keyword (để so sánh khi đánh giá)."""
    if _chunks is None:
        _load()
    kw = _keyword_scores(query)
    kw_max = max(kw) or 1.0
    use_vec = mode != "keyword" and _ensure_embeddings()
    qv = None
    if use_vec:
        try:
            qv = _embed([query])[0]
        except Exception as e:
            log.warning("RAG: lỗi embedding câu hỏi (%s) — dùng từ khóa", e)
    topic_files = set(TOPIC_FILES.get(topic, []))
    scored = []
    for c, ks in zip(_chunks, kw):
        sem = sum(a * b for a, b in zip(qv, c["vec"])) if qv is not None else 0.0
        kn = ks / kw_max
        if mode == "semantic" and qv is not None:
            score = sem
        elif qv is None or mode == "keyword":
            score = kn
        else:
            score = W_SEMANTIC * sem + W_KEYWORD * kn
        if c["file"] in topic_files and mode == "hybrid":
            score += W_TOPIC
        scored.append({"file": c["file"], "text": c["text"], "score": score, "semantic": sem, "keyword": kn})
    scored.sort(key=lambda x: -x["score"])
    return scored[:k]


def retrieve(query: str, topic: str = "general", k: int = 3) -> list[str]:
    return [h["text"] for h in search(query, topic, k)]

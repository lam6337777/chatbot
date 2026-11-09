"""Client LLM tương thích OpenAI (Ollama local hoặc cloud)."""
import json
import logging
import re

from openai import OpenAI

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MAX_TOKENS, LLM_MODEL, LLM_PROVIDER, LLM_TEMPERATURE
from .text import clean_llm_output

log = logging.getLogger("pf_bot.llm")

_client = OpenAI(api_key=LLM_API_KEY or "none", base_url=LLM_BASE_URL, timeout=90, max_retries=0)

# Gemini 2.5 mặc định "suy nghĩ" trước khi trả lời; phần này tính vào max_tokens và làm chậm —
# chatbot đã có dữ liệu/tài liệu sẵn nên tắt đi.
_EXTRA = {"reasoning_effort": "none"} if LLM_PROVIDER == "gemini" else {}


class LLMUnavailable(Exception):
    pass


def describe() -> str:
    return f"{LLM_PROVIDER} · {LLM_MODEL}"


def complete_json(system: str, user: str, max_tokens: int = 200) -> dict:
    """Gọi LLM và parse JSON; trả {} nếu model trả về rác."""
    try:
        resp = _client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            **_EXTRA,
        )
    except Exception as e:  # kết nối / model chưa tải
        log.error("LLM json error: %s", e)
        raise LLMUnavailable(str(e)) from None
    raw = resp.choices[0].message.content or ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    log.warning("LLM trả JSON không hợp lệ: %r", raw[:200])
    return {}


def stream_text(system: str, messages: list[dict], max_tokens: int | None = None):
    """Yield từng đoạn text. Ném LLMUnavailable nếu không gọi được model."""
    try:
        stream = _client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": system}, *messages],
            temperature=LLM_TEMPERATURE,
            max_tokens=max_tokens or LLM_MAX_TOKENS,
            stream=True,
            **_EXTRA,
        )
    except Exception as e:
        log.error("LLM stream error: %s", e)
        raise LLMUnavailable(str(e)) from None
    try:
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                cleaned = clean_llm_output(delta)
                if cleaned:
                    yield cleaned
    except Exception as e:
        log.error("LLM stream interrupted: %s", e)
        raise LLMUnavailable(str(e)) from None

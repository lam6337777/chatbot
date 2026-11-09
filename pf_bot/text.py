"""Tiện ích xử lý tiếng Việt: bỏ dấu, chuẩn hóa, định dạng tiền."""
import re
import unicodedata

_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯＀-￯]+")
_PLACEHOLDER = re.compile(r"\{\{.*?\}\}")


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def norm(s: str) -> str:
    """Chữ thường, bỏ dấu, gộp khoảng trắng — dùng để so khớp quy tắc."""
    s = strip_accents(s or "").lower()
    s = re.sub(r"[^\w\s.,\-/<>~]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def has_any(text: str, phrases) -> bool:
    """text đã norm(); khớp theo ranh giới từ."""
    return any(re.search(rf"(?<!\w){re.escape(p)}(?!\w)", text) for p in phrases)


def vnd(value) -> str:
    try:
        return f"{int(round(float(value))):,}".replace(",", ".") + "đ"
    except (TypeError, ValueError):
        return "—"


def clean_llm_output(s: str) -> str:
    """Model nhỏ thỉnh thoảng chèn chữ Trung/Nhật hoặc biến mẫu chưa thay — loại bỏ."""
    s = _CJK.sub("", s)
    s = _PLACEHOLDER.sub("", s)
    return s

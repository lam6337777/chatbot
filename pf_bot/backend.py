"""Client gọi REST API của backend. Chỉ dùng thư viện chuẩn để không thêm phụ thuộc."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .config import BACKEND_API_URL


class BackendError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _request(method: str, path: str, params=None, jwt: str | None = None, timeout: float = 8):
    url = f"{BACKEND_API_URL}{path}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        if clean:
            url += "?" + urllib.parse.urlencode(clean, doseq=True)
    req = urllib.request.Request(url, method=method)
    req.add_header("Accept", "application/json")
    if jwt:
        req.add_header("Authorization", f"Bearer {jwt}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read() or b"{}").get("message") or e.reason
        except Exception:
            msg = e.reason
        raise BackendError(e.code, str(msg)) from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise BackendError(503, f"Không kết nối được backend: {e}") from None
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def get(path, params=None, jwt=None, timeout=8):
    return _request("GET", path, params, jwt, timeout)


# ── Cache nhỏ cho dữ liệu ít thay đổi (danh mục, thương hiệu) ──────────────────
_cache: dict[str, tuple[float, object]] = {}


def cached_get(path, ttl=600):
    hit = _cache.get(path)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    data = get(path)
    _cache[path] = (time.time(), data)
    return data


# ── Xác thực người dùng từ JWT (không tin userid do client gửi lên) ────────────
_user_cache: dict[str, tuple[float, dict]] = {}


def current_user(jwt: str | None) -> dict | None:
    if not jwt:
        return None
    hit = _user_cache.get(jwt)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    try:
        user = get("/users/me", jwt=jwt, timeout=5)
    except BackendError:
        return None
    if not isinstance(user, dict) or "id" not in user:
        return None
    if len(_user_cache) > 500:
        _user_cache.clear()
    _user_cache[jwt] = (time.time(), user)
    return user

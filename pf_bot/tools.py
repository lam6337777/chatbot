"""Công cụ lấy dữ liệu thật qua REST API của backend.

Mỗi hàm trả về dict gọn để bot dựng câu trả lời; không truy cập DB trực tiếp nên
mọi quy tắc nghiệp vụ (giá hiệu lực, phí ship, quyền xem đơn) do backend quyết định.
"""
from . import backend
from .text import vnd

ORDER_STATUS = {
    "PENDING": "Chờ xác nhận", "CONFIRMED": "Đã xác nhận", "SHIPPING": "Đang giao", "DELIVERED": "Đã giao",
    "CANCELLED": "Đã hủy", "RETURN_REQUESTED": "Đang yêu cầu trả hàng", "RETURNED": "Đã trả hàng",
    "PARTIALLY_RETURNED": "Đã trả một phần", "EXCHANGE_REQUESTED": "Đang yêu cầu đổi hàng", "EXCHANGED": "Đã đổi hàng",
    "WARRANTY_REQUESTED": "Đang yêu cầu bảo hành", "WARRANTY_REPAIRING": "Đang bảo hành", "WARRANTY_COMPLETED": "Bảo hành xong",
}
PAYMENT_STATUS = {"UNPAID": "chưa thanh toán", "PENDING": "chờ thanh toán", "PAID": "đã thanh toán",
                  "COMPLETED": "đã thanh toán", "REFUNDED": "đã hoàn tiền", "PARTIALLY_REFUNDED": "đã hoàn tiền một phần"}


def _card(p: dict, size: str | None = None) -> dict:
    variants = p.get("variants") or []
    in_stock = sorted({v["size"] for v in variants if (v.get("stockQuantity") or 0) > 0},
                      key=lambda s: float(s) if s.replace(".", "").isdigit() else 0)
    images = p.get("images") or []
    primary = next((i for i in images if i.get("isPrimary")), images[0] if images else None)
    price = p.get("salePrice") or p.get("originalPrice")
    card = {
        "id": p["id"],
        "name": p["name"],
        "price": price,
        "originalPrice": p.get("originalPrice") if p.get("salePrice") else None,
        "image": primary.get("imageUrl") if primary else None,
        "category": p.get("categoryName"),
        "rating": p.get("avgRating") or 0,
        "sizesInStock": in_stock,
        "url": f"/products/{p['id']}",
    }
    if size:
        stock = sum((v.get("stockQuantity") or 0) for v in variants if v.get("size") == size)
        card["sizeStock"] = stock
    return card


def search_products(brand=None, category=None, size=None, min_price=None, max_price=None, on_sale=None,
                    sort=None, keyword=None, limit=4) -> dict:
    params = dict(brandName=brand, categoryName=category, productSize=size, minPrice=min_price, maxPrice=max_price,
                  onSale="true" if on_sale else None, sortBy=sort or ("best_selling" if not keyword else "newest"),
                  q=keyword, size=limit, page=0)
    data = backend.get("/products", params)
    relaxed = None
    # Từ khóa do quy tắc tách ra có thể chứa từ thừa → thử lại không có từ khóa
    if data.get("totalElements", 0) == 0 and keyword:
        params["q"] = None
        params["sortBy"] = sort or "best_selling"
        data = backend.get("/products", params)
        relaxed = "keyword"
    return {
        "total": data.get("totalElements", 0),
        "products": [_card(p, size) for p in data.get("content", [])],
        "relaxed": relaxed,
    }


def shipping_quote(province: str | None, subtotal: float | None = None) -> dict:
    return backend.get("/shipping/quote", {"province": province, "subtotal": subtotal})


def vouchers() -> list[dict]:
    return backend.get("/vouchers/available") or []


def voucher_line(v: dict) -> str:
    if v.get("discountType") == "PERCENT":
        value = f"giảm {float(v['discountValue']):g}%"
        if v.get("maxDiscount"):
            value += f" (tối đa {vnd(v['maxDiscount'])})"
    else:
        value = f"giảm {vnd(v['discountValue'])}"
    cond = f" cho đơn từ {vnd(v['minOrderValue'])}" if v.get("minOrderValue") else ""
    end = f", hạn đến {v['endAt'][8:10]}/{v['endAt'][5:7]}/{v['endAt'][:4]}" if v.get("endAt") else ""
    return f"**{v['code']}**: {value}{cond}{end}"


def my_orders(jwt: str, limit=5) -> list[dict]:
    data = backend.get("/orders", {"page": 0, "size": limit}, jwt=jwt)
    return data.get("content", []) if isinstance(data, dict) else []


def order_detail(code: str, jwt: str) -> dict:
    return backend.get(f"/orders/{code}", jwt=jwt)


def order_line(o: dict) -> str:
    status = ORDER_STATUS.get(o.get("status"), o.get("status"))
    items = o.get("items") or []
    first = items[0]["productName"] if items else ""
    more = f" và {len(items) - 1} sản phẩm khác" if len(items) > 1 else ""
    date = (o.get("createdAt") or "")[:10]
    date = f"{date[8:10]}/{date[5:7]}/{date[:4]}" if date else ""
    return f"[#{o['orderCode']}](/account/orders/{o['orderCode']}) · {date} · {first}{more} · {vnd(o.get('totalAmount'))} · **{status}**"

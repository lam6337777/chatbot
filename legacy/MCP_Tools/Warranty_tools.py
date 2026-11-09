import os
import json
from db_client import db_client

class Warranty_tools:
    """Tools for managing warranty, returns, and exchanges tied to database records."""

    # Policy reading removed: handled by Policy_tools.get_policy


    def check_warranty_eligibility(self, order_id):
        """Check DB for order creation date to verify if it is within the warranty period (e.g., 7 days for return)."""
        sql = "SELECT id, created_at, status FROM orders WHERE order_code = %s"
        res = db_client.execute_query(sql, (order_id,))
        if not res: return "Mã đơn không tồn tại."
        return json.dumps(res[0], ensure_ascii=False, default=str)

    def check_return_eligibility(self, order_id, product_id=None, reason=None):
        """Check if a specific product from an order is eligible for return/exchange."""
        order_info_raw = self.check_warranty_eligibility(order_id)
        if "Mã đơn không tồn tại" in order_info_raw: return order_info_raw
        
        try:
            data = json.loads(order_info_raw)
            eligible = data.get("status") == "DELIVERED"
            # Logic thực tế có thể check thêm ngày so với created_at (ví dụ 7 ngày)
            return json.dumps({
                "eligible": eligible,
                "reason": reason or "N/A",
                "allowed_actions": ["return", "exchange"] if eligible else ["warranty"],
                "message": "Sản phẩm đủ điều kiện" if eligible else "Đã quá hạn đổi trả 7 ngày hoặc chưa giao hàng thành công."
            }, ensure_ascii=False)
        except:
            return "Lỗi xử lý dữ liệu đơn hàng."

    def get_warranty_status(self, product_id, purchase_date=None):
        """Check warranty status for a product based on its category."""
        # Simple logic based on ID prefix if DB doesn't have warranty table yet
        if product_id and "SHO" in product_id.upper(): remaining = "6 tháng"
        elif product_id and "ACC" in product_id.upper(): remaining = "1 tháng"
        else: remaining = "3 tháng"
        return json.dumps({"product_id": product_id, "warranty_remaining": remaining, "coverage": "Lỗi nhà sản xuất (bong keo, đứt chỉ, nứt đế)"}, ensure_ascii=False)

    def submit_return_request(self, order_id, items, reason, request_type):
        """Submit a return/exchange request for processing."""
        # In real app, this would INSERT into a return_requests table
        request_id = f"RT-{order_id}-001"
        return json.dumps({"request_id": request_id, "status": "PENDING", "message": f"Yêu cầu {request_type} cho đơn {order_id} đã được ghi nhận."}, ensure_ascii=False)

    def get_return_status(self, request_id):
        """Track status of a return/exchange request."""
        # Mocking a response
        return json.dumps({"request_id": request_id, "status": "PROCESSING", "details": "Đã nhận hàng, đang kiểm tra."}, ensure_ascii=False)

    def get_return_address(self):
        """Get address for sending returns."""
        return json.dumps({
            "address": "Số 123, Đường ABC, Phường XYZ, Quận 1, TP.HCM", 
            "recipient": "Trung tâm Đổi trả PF", 
            "phone": "028 1234 5678"
        }, ensure_ascii=False)

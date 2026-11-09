import os
import json

DATA_DIR = "Data_policy"

class Policy_tools:
    """Tools for retrieving official store policies and general store information."""

    def get_policy(self, policy_type):
        """Retrieve the raw content of a specific policy file."""
        mapping = {
            "shipping": "shipping_policy.txt.txt",
            "warranty": "warranty_policy.txt.txt",
            "return": "return_refund_policy.txt.txt",
            "faq": "faq.txt.txt",
            "privacy": "privacy_policy.txt.txt",
            "sales": "sales_policy.txt.txt",
            "payment": "payment_policy.txt.txt"
        }
        file_name = mapping.get(policy_type.lower())
        if not file_name: return json.dumps({"error": "Không tìm thấy chủ đề chính sách này."}, ensure_ascii=False)
        path = os.path.join(DATA_DIR, file_name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.dumps({"content": f.read()}, ensure_ascii=False)
        return json.dumps({"error": f"File {file_name} không tồn tại trong Data_policy."}, ensure_ascii=False)

    # --- Shipping & Legacy Tools ---
    def get_shipping_fee(self, province, weight=0, district=""):
        """Calculate estimated shipping fee based on destination and weight."""
        prov = province.lower()
        if "hồ chí minh" in prov or "hcm" in prov: fee = 20000
        elif "hà nội" in prov: fee = 35000
        else: fee = 45000
        if weight and weight > 5: fee += 20000
        return json.dumps({"province": province, "fee": fee, "currency": "VNĐ"}, ensure_ascii=False)

    def validate_voucher_code(self, voucher_code, cart_total=0):
        """Check if a voucher code is valid and calculate discount."""
        vouchers = {"PF20": 0.2, "PF10": 0.1, "WELCOME": 50000}
        c = str(voucher_code).upper()
        if c in vouchers:
            discount = vouchers[c]
            return json.dumps({"valid": True, "discount": f"{discount*100}%" if discount < 1 else f"{discount} VNĐ"}, ensure_ascii=False)
        return json.dumps({"valid": False, "reason": "Mã không tồn tại."}, ensure_ascii=False)

    def handle_account_request(self, user_id):
        """Process account-related requests (reset_password)."""
        return json.dumps({"status": "SUCCESS", "message": f"Yêu cầu cho user {user_id} đã được tiếp nhận. Đã gửi link reset vào Email/SMS."}, ensure_ascii=False)


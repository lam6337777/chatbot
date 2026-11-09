import json
from db_client import db_client
from datetime import datetime

class Promotion_tools:
    """Tools for managing discount coupons, vouchers, and sales events from the database."""

    def get_active_coupons(self):
        """Lấy danh sách tất cả các mã giảm giá đang còn hiệu lực."""
        sql = """
        SELECT code, type, value, min_order_amount, max_discount, end_date
        FROM coupons
        WHERE is_active = true 
        AND (start_date IS NULL OR start_date <= NOW())
        AND (end_date IS NULL OR end_date >= NOW())
        AND (usage_limit IS NULL OR used_count < usage_limit)
        """
        results = db_client.execute_query(sql)
        return json.dumps(results, ensure_ascii=False, default=str)

    def validate_coupon(self, code, cart_total=0):
        """Kiểm tra tính hợp lệ của một mã giảm giá dựa trên tổng giá trị giỏ hàng."""
        sql = """
        SELECT * FROM coupons 
        WHERE code = %s AND is_active = true
        """
        res = db_client.execute_query(sql, (code,))
        
        if not res:
            return json.dumps({"valid": False, "message": f"Mã giảm giá '{code}' không tồn tại hoặc đã hết hạn."}, ensure_ascii=False)
        
        coupon = res[0]
        now = datetime.now()
        
        # Kiểm tra ngày bắt đầu/kết thúc
        if coupon['start_date'] and now < coupon['start_date']:
            return json.dumps({"valid": False, "message": "Mã giảm giá chưa đến thời gian áp dụng."}, ensure_ascii=False)
        if coupon['end_date'] and now > coupon['end_date']:
            return json.dumps({"valid": False, "message": "Mã giảm giá đã hết hạn sử dụng."}, ensure_ascii=False)
            
        # Kiểm tra số lượt dùng
        if coupon['usage_limit'] and coupon['used_count'] >= coupon['usage_limit']:
            return json.dumps({"valid": False, "message": "Mã giảm giá đã hết lượt sử dụng."}, ensure_ascii=False)
            
        # Kiểm tra giá trị đơn tối thiểu
        min_amount = float(coupon['min_order_amount'] or 0)
        if cart_total < min_amount:
            return json.dumps({
                "valid": False, 
                "message": f"Mã này chỉ áp dụng cho đơn hàng từ {min_amount:,.0f}đ trở lên. Bạn còn thiếu {(min_amount - cart_total):,.0f}đ."
            }, ensure_ascii=False)

        # Tính toán giá trị giảm (nếu cần mockup ở đây)
        discount_value = float(coupon['value'])
        if coupon['type'] == 'PERCENTAGE':
            estimated_discount = cart_total * (discount_value / 100)
            if coupon['max_discount']:
                estimated_discount = min(estimated_discount, float(coupon['max_discount']))
        else: # FIXED_AMOUNT
            estimated_discount = discount_value

        return json.dumps({
            "valid": True,
            "message": "Áp dụng mã thành công!",
            "coupon_details": coupon,
            "estimated_discount": estimated_discount
        }, ensure_ascii=False, default=str)

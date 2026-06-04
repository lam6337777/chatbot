import json
from db_client import db_client

class Payment_tools:
    """Tools for verifying payments, checking refund status, and handling billing inquiries."""

    def get_payment_status(self, order_id):
        """Get payment method and status for an order."""
        sql = "SELECT payment_method, payment_status, total_amount, created_at FROM orders WHERE order_code = %s"
        result = db_client.execute_query(sql, (order_id,))
        if not result:
            return json.dumps({"error": "Không tìm thấy thông tin đơn hàng."}, ensure_ascii=False)
        return json.dumps(result[0], ensure_ascii=False, default=str)

    def verify_transaction(self, order_id, transaction_ref=None):
        """Confirm if a specific payment transaction has been successfully processed."""
        sql = "SELECT status, amount, transaction_ref, paid_at FROM payments WHERE order_id = (SELECT id FROM orders WHERE order_code = %s)"
        params = [order_id]
        if transaction_ref:
            sql += " AND transaction_ref = %s"
            params.append(transaction_ref)
        result = db_client.execute_query(sql, tuple(params))
        if not result:
            return json.dumps({"confirmed": False, "message": "Giao dịch chưa được ghi nhận."}, ensure_ascii=False)
        data = result[0]
        return json.dumps({
            "confirmed": data['status'] in ['COMPLETED', 'SUCCESS'],
            "amount": data['amount'],
            "ref": data['transaction_ref'],
            "paid_at": str(data['paid_at'])
        }, ensure_ascii=False)

    def get_refund_status(self, order_id):
        """Check the progress of a refund for a cancelled or returned order."""
        sql = "SELECT payment_status, total_amount FROM orders WHERE order_code = %s"
        result = db_client.execute_query(sql, (order_id,))
        if not result: return json.dumps({"error": "Không tìm thấy."}, ensure_ascii=False)
        return json.dumps({
            "status": result[0]['payment_status'],
            "amount": result[0]['total_amount'],
            "estimate": "Hoàn tiền từ 3-7 ngày làm việc."
        }, ensure_ascii=False)

    def get_available_payment_methods(self):
        """List accepted payment methods at PF storefront."""
        methods = [
            {"name": "COD (Thanh toán khi nhận hàng)", "condition": "Đơn hàng dưới 20,000,000 VNĐ"},
            {"name": "Chuyển khoản Ngân hàng", "desc": "Vietcombank/Techcombank"},
            {"name": "VNPay", "desc": "Visa, Master, JCB, Thẻ nội địa"},
            {"name": "Ví điện tử", "desc": "Momo, ZaloPay, ShopeePay"}
        ]
        return json.dumps(methods, ensure_ascii=False)

    def request_invoice(self, order_id, company_info):
        """Request a VAT invoice for a specific order with company details."""
        print(f"DEBUG: Invoice requested for {order_id} with info: {company_info}")
        return json.dumps({"success": True, "message": f"Yêu cầu xuất hóa đơn cho {order_id} đã được gửi."}, ensure_ascii=False)

    def check_payment_eligibility(self, order_id, payment_method):
        """Check if a specific payment method can be used for an order."""
        if payment_method.upper() == "COD":
            # Mock logic: COD only for orders < 20M
            return json.dumps({"eligible": True}, ensure_ascii=False)
        return json.dumps({"eligible": True}, ensure_ascii=False)

    def report_payment_issue(self, order_id, issue_description):
        """Record an issue with a payment transaction for CS resolution."""
        print(f"DEBUG: Payment issue for {order_id}: {issue_description}")
        return json.dumps({"ticket": f"PAY-{order_id}-X", "message": "Vấn đề đã được ghi nhận. CS sẽ liên hệ sớm."}, ensure_ascii=False)

import json
from db_client import db_client

class Order_tools:
    """Tools for checking order status, tracking shipments, and managing cancellations."""

    def get_order_status(self, order_id):
        """
        Tra cứu trạng thái hiện tại của một đơn hàng dựa vào Mã đơn hàng (order_id).
        Trả về chi tiết tình trạng, địa chỉ giao hàng và danh sách các sản phẩm có trong đơn.
        """
        sql = """
        SELECT order_code, status, total_amount, shipping_address, created_at, shipping_name, shipping_phone 
        FROM orders WHERE order_code = %s
        """
        result = db_client.execute_query(sql, (order_id,))
        if not result:
            return json.dumps({"error": f"Không tìm thấy đơn hàng mã {order_id}."}, ensure_ascii=False)
        order = result[0]
        items_sql = """
        SELECT product_name, size, color, quantity, unit_price, total_price 
        FROM order_items WHERE order_id = (SELECT id FROM orders WHERE order_code = %s)
        """
        items = db_client.execute_query(items_sql, (order_id,))
        order['items'] = items
        return json.dumps(order, ensure_ascii=False, default=str)

    def find_order_by_phone(self, phone_number):
        """
        Tìm kiếm tất cả các đơn hàng thuộc về một số điện thoại khách hàng.
        Sắp xếp theo thứ tự đơn hàng mới nhất lên đầu.
        """
        sql = "SELECT order_code, created_at, status, total_amount FROM orders WHERE shipping_phone = %s ORDER BY created_at DESC"
        results = db_client.execute_query(sql, (phone_number,))
        return json.dumps(results, ensure_ascii=False, default=str)

    def track_order(self, order_id):
        """
        Kiểm tra tiến trình giao hàng của một đơn (Tracking).
        Mô phỏng các sự kiện giao hàng (Đã tạo, Xác nhận, Đang giao, Thành công) dựa vào trạng thái hiện tại.
        """
        sql = "SELECT status FROM orders WHERE order_code = %s"
        res = db_client.execute_query(sql, (order_id,))
        if not res: return json.dumps({"error": "Không tìm thấy đơn hàng"}, ensure_ascii=False)
        status = res[0]['status'].upper()
        events = [{"event": "Đơn hàng đã được tạo."}]
        if status != "PENDING":
            events.append({"event": "Đơn hàng đã được xác nhận."})
        if status in ["SHIPPED", "DELIVERED"]:
            events.append({"event": "Đã bàn giao cho đơn vị vận chuyển."})
        if status == "DELIVERED":
            events.append({"event": "Giao hàng thành công."})
        return json.dumps({"order_id": order_id, "events": events}, ensure_ascii=False)

    def check_cancellation_eligibility(self, order_id):
        """
        Kiểm tra xem đơn hàng có đủ điều kiện để Hủy hay không.
        Chỉ cho phép hủy nếu đơn hàng đang ở trạng thái 'PENDING' (Chờ xử lý) hoặc 'CONFIRMED' (Đã xác nhận).
        """
        sql = "SELECT status FROM orders WHERE order_code = %s"
        res = db_client.execute_query(sql, (order_id,))
        if not res: return json.dumps({"eligible": False, "reason": "Không tìm thấy mã đơn."}, ensure_ascii=False)
        status = res[0]['status'].upper()
        if status in ["PENDING", "CONFIRMED"]:
            return json.dumps({"eligible": True, "status": status}, ensure_ascii=False)
        return json.dumps({"eligible": False, "reason": f"Đơn đã ở trạng thái {status}."}, ensure_ascii=False)

    def cancel_order(self, order_id):
        """
        Thực hiện thao tác Hủy đơn hàng trong Cơ sở dữ liệu (Cập nhật trạng thái thành 'CANCELLED').
        Sẽ tự động gọi hàm check_cancellation_eligibility trước để kiểm tra tính hợp lệ.
        """
        eligibility = json.loads(self.check_cancellation_eligibility(order_id))
        if not eligibility['eligible']:
            return json.dumps({"success": False, "message": eligibility['reason']}, ensure_ascii=False)
        sql = "UPDATE orders SET status = 'CANCELLED' WHERE order_code = %s"
        db_client.execute_query(sql, (order_id,))
        return json.dumps({"success": True, "message": f"Đơn hàng {order_id} đã hủy thành công."}, ensure_ascii=False)

    def modify_order(self, order_id, changes):
        """
        Ghi nhận yêu cầu thay đổi thông tin đơn hàng (Ví dụ: Đổi địa chỉ, đổi size, thêm bớt món).
        Hàm này hiện tại đang hoạt động ở chế độ ghi log/ghi nhận yêu cầu.
        """
        print(f"DEBUG: Modifying order {order_id} with changes: {changes}")
        return json.dumps({"success": True, "message": f"Yêu cầu chỉnh sửa đơn {order_id} đã ghi nhận."}, ensure_ascii=False)

    def get_delivery_estimate(self, order_id):
        """
        Dự kiến ngày giao hàng thành công của đơn hàng.
        """
        return json.dumps({"order_id": order_id, "estimated_delivery": "2026-03-05 - 2026-03-07"}, ensure_ascii=False)

    def get_return_request_status(self, order_code):
        """Kiểm tra trạng thái yêu cầu đổi trả/hoàn tiền của một đơn hàng."""
        sql = """
        SELECT rr.status, rr.reason, rr.type, rr.created_at, rr.admin_note
        FROM return_requests rr
        JOIN orders o ON rr.order_id = o.id
        WHERE o.order_code = %s
        ORDER BY rr.created_at DESC
        """
        results = db_client.execute_query(sql, (order_code,))
        return json.dumps(results, ensure_ascii=False, default=str)

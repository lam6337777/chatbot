import json
import os
from db_client import db_client

DATA_DIR = "Data_policy"

class Product_tools:
    """Tools for searching and retrieving product, stock, and size information."""

    def search_products(self, brand=None, category=None, size=None, color=None, min_price=None, max_price=None, in_stock_only=False, limit=5):
        """
        Tìm kiếm giày dựa trên nhiều tiêu chí lọc (Hãng, Danh mục, Size, Màu, Giá).
        Trả về danh sách tóm tắt các đôi giày thỏa mãn điều kiện.
        """
        sql = """
        SELECT 
            p.id, p.name, p.sale_price, p.original_price,
            c.name as category_name, b.name as brand_name,
            array_agg(DISTINCT v.size) as sizes,
            array_agg(DISTINCT v.color) as colors
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN brands b ON p.brand_id = b.id
        LEFT JOIN product_variants v ON p.id = v.product_id
        WHERE p.is_active = true
        """
        params = []
        if brand:
            sql += " AND b.name ILIKE %s"
            params.append(f"%{brand}%")
        if category:
            sql += " AND c.name ILIKE %s"
            params.append(f"%{category}%")
        if min_price:
            sql += " AND COALESCE(p.sale_price, p.original_price) >= %s"
            params.append(min_price)
        if max_price:
            sql += " AND COALESCE(p.sale_price, p.original_price) <= %s"
            params.append(max_price)
        if in_stock_only:
            sql += " AND v.stock_quantity > 0"
        
        sql += " GROUP BY p.id, c.name, b.name ORDER BY p.created_at DESC LIMIT %s"
        params.append(limit)
        
        results = db_client.execute_query(sql, tuple(params))
        return json.dumps(results, ensure_ascii=False, default=str)

    def get_product_details(self, product_id):
        """
        Lấy toàn bộ thông tin chi tiết của một đôi giày cụ thể (dựa vào ID).
        Bao gồm cả thông tin về các biến thể (size, màu sắc) và số lượng tồn kho.
        """
        sql = """
        SELECT p.*, c.name as category_name, b.name as brand_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN brands b ON p.brand_id = b.id
        WHERE p.id = %s
        """
        product = db_client.execute_query(sql, (product_id,))
        if not product:
            return json.dumps({"error": "Sản phẩm không tồn tại."}, ensure_ascii=False)
        
        variant_sql = "SELECT size, color, stock_quantity, sku FROM product_variants WHERE product_id = %s"
        variants = db_client.execute_query(variant_sql, (product_id,))
        
        result = product[0]
        result['variants'] = variants
        return json.dumps(result, ensure_ascii=False, default=str)

    def check_availability(self, product_id, size=None, color=None):
        """
        Kiểm tra số lượng tồn kho của một đôi giày.
        Có thể kiểm tra tồn kho tổng, hoặc tồn kho chi tiết theo từng Size và Màu cụ thể.
        """
        sql = "SELECT size, color, stock_quantity FROM product_variants WHERE product_id = %s"
        params = [product_id]
        if size:
            sql += " AND size = %s"
            params.append(size)
        if color:
            sql += " AND color = %s"
            params.append(color)
            
        results = db_client.execute_query(sql, tuple(params))
        total_stock = sum(r['stock_quantity'] for r in results) if results else 0
        return json.dumps({"available": total_stock > 0, "stock": total_stock, "details": results}, ensure_ascii=False)

    def get_price(self, product_id):
        """
        Tra cứu giá bán hiện tại và giá gốc của một đôi giày.
        Đồng thời cho biết đôi giày này có đang được giảm giá hay không.
        """
        sql = "SELECT name, original_price, sale_price FROM products WHERE id = %s"
        res = db_client.execute_query(sql, (product_id,))
        if not res: return json.dumps({"error": "Sản phẩm không tồn tại"}, ensure_ascii=False)
        data = res[0]
        return json.dumps({
            "name": data['name'], 
            "price": data['sale_price'] or data['original_price'],
            "original_price": data['original_price'],
            "on_sale": data['sale_price'] is not None
        }, ensure_ascii=False)

    def get_size_chart(self, brand, product_line=None):
        """
        Đọc file văn bản để lấy bảng hướng dẫn chọn Size giày.
        Hỗ trợ lấy bảng size theo từng hãng (Nike, Adidas) hoặc dòng sản phẩm cụ thể.
        """
        chart_path = os.path.join(DATA_DIR, "size_guild.txt.txt")
        if os.path.exists(chart_path):
            with open(chart_path, "r", encoding="utf-8") as f:
                content = f.read()
                if brand.lower() in content.lower():
                    return f"Bảng size cho {brand} {'(' + product_line + ')' if product_line else ''}:\n" + content
                return content
        return "Không tìm thấy bảng size."

    def get_recommendations(self, purpose=None, budget=None, brand_preference=None):
        """
        Gợi ý giày thông minh dựa trên nhu cầu của khách hàng (Mục đích sử dụng, Ngân sách, Hãng yêu thích).
        Hàm này sẽ random ra 3 đôi giày ngẫu nhiên thỏa mãn điều kiện để tư vấn.
        """
        sql = """
        SELECT p.id, p.name, COALESCE(p.sale_price, p.original_price) as price, b.name as brand_name
        FROM products p
        LEFT JOIN brands b ON p.brand_id = b.id
        WHERE p.is_active = true
        """
        params = []
        if purpose:
            sql += " AND (p.description ILIKE %s OR p.name ILIKE %s)"
            params.extend([f"%{purpose}%", f"%{purpose}%"])
        if budget:
            sql += " AND COALESCE(p.sale_price, p.original_price) <= %s"
            params.append(budget)
        if brand_preference:
            sql += " AND b.name ILIKE %s"
            params.append(f"%{brand_preference}%")
        sql += " ORDER BY RANDOM() LIMIT 3"
        results = db_client.execute_query(sql, tuple(params))
        return json.dumps(results, ensure_ascii=False, default=str)

    def get_new_arrivals(self, limit=5):
        """
        Lấy danh sách các đôi giày mới nhất vừa được nhập về cửa hàng (dựa vào ngày tạo mới nhất).
        """
        return self.search_products(limit=limit)

    def get_similar_products(self, product_id, limit=3):
        """
        Gợi ý các đôi giày có nét tương đồng với đôi giày khách đang xem.
        Thuật toán hiện tại là tìm các đôi giày nằm trong cùng Danh mục (Category) với đôi giày gốc.
        """
        # First get the category of the source product
        source = db_client.execute_query("SELECT category_id FROM products WHERE id = %s", (product_id,))
        cat_id = source[0]['category_id'] if source else None
        
        sql = """
        SELECT p.id, p.name, p.sale_price, p.original_price, b.name as brand_name
        FROM products p
        LEFT JOIN brands b ON p.brand_id = b.id
        WHERE p.is_active = true AND p.id != %s
        """
        params = [product_id]
        if cat_id:
            sql += " AND p.category_id = %s"
            params.append(cat_id)
        
        sql += " ORDER BY RANDOM() LIMIT %s"
        params.append(limit)
        
        results = db_client.execute_query(sql, tuple(params))
        return json.dumps(results, ensure_ascii=False, default=str)

    def get_product_reviews(self, product_id):
        """Lấy danh sách đánh giá của khách hàng cho một sản phẩm cụ thể."""
        sql = """
        SELECT r.rating, r.comment, r.created_at, u.full_name
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.product_id = %s
        ORDER BY r.created_at DESC
        """
        results = db_client.execute_query(sql, (product_id,))
        return json.dumps(results, ensure_ascii=False, default=str)

    def get_top_rated_products(self, limit=5):
        """Lấy danh sách các sản phẩm có điểm đánh giá cao nhất."""
        sql = """
        SELECT p.id, p.name, p.avg_rating, p.review_count, p.sale_price, p.original_price
        FROM products p
        WHERE p.is_active = true AND p.review_count > 0
        ORDER BY p.avg_rating DESC, p.review_count DESC
        LIMIT %s
        """
        results = db_client.execute_query(sql, (limit,))
        return json.dumps(results, ensure_ascii=False, default=str)

    def get_product_by_name(self, name):
        """Tìm chi tiết sản phẩm dựa trên tên chính xác hoặc gần đúng."""
        sql = """
        SELECT id FROM products 
        WHERE name ILIKE %s AND is_active = true 
        ORDER BY LENGTH(name) ASC LIMIT 1
        """
        res = db_client.execute_query(sql, (f"%{name}%",))
        if not res:
            return json.dumps({"error": f"Không tìm thấy sản phẩm có tên '{name}'"}, ensure_ascii=False)
        return self.get_product_details(res[0]['id'])

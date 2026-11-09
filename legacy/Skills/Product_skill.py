import json
import time
from Skills.Base_skill import BaseSkill
from MCP_Tools.Product_tools import Product_tools

class ProductSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="Product Skill",
            description="Tìm kiếm sản phẩm, kiểm tra tồn kho, xem chi tiết và đánh giá sản phẩm.",
            prompt_filename="Product.txt"
        )
        self.product_tools = Product_tools()
        
        # Đăng ký các công cụ thực tế
        self.tools_dict = {
            "search_products": self.product_tools.search_products,
            "get_product_details": self.product_tools.get_product_details,
            "check_availability": self.product_tools.check_availability,
            "get_new_arrivals": self.product_tools.get_new_arrivals,
            "get_similar_products": self.product_tools.get_similar_products,
            "get_product_reviews": self.product_tools.get_product_reviews,
            "get_top_rated_products": self.product_tools.get_top_rated_products,
            "get_product_by_name": self.product_tools.get_product_by_name,
        }

        # Định nghĩa schema cho Tool Calling
        self.tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "search_products",
                    "description": "Tìm sản phẩm theo bộ lọc: thương hiệu, danh mục, kích thước, màu sắc, khoảng giá.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "brand": {"type": "string"},
                            "category": {"type": "string"},
                            "size": {"type": "string"},
                            "color": {"type": "string"},
                            "min_price": {"type": "integer"},
                            "max_price": {"type": "integer"},
                            "in_stock_only": {"type": "boolean"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_product_details",
                    "description": "Lấy thông tin chi tiết và các biến thể của một sản phẩm qua ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"}
                        },
                        "required": ["product_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_availability",
                    "description": "Kiểm tra số lượng tồn kho của một biến thể sản phẩm cụ thể.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "size": {"type": "string"},
                            "color": {"type": "string"}
                        },
                        "required": ["product_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_new_arrivals",
                    "description": "Lấy danh sách các sản phẩm mới nhất.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_product_by_name",
                    "description": "Tìm kiếm thông tin sản phẩm qua tên.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"}
                        },
                        "required": ["name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_recommendations",
                    "description": "Gợi ý sản phẩm dựa trên mục đích sử dụng, ngân sách hoặc hãng yêu thích.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "purpose": {"type": "string"},
                            "budget": {"type": "integer"},
                            "brand_preference": {"type": "string"}
                        }
                    }
                }
            }
        ]

    def handle_query(self, user_input: str, history: str = "") -> dict:
        print(f" [{self.name}] Đang xử lý: {user_input}")
        timings = {}
        
        # 1. Gọi LLM để trích xuất tool calls
        t_start = time.time()
        tool_prompt = f"Lịch sử hội thoại:\n{history}\n\nCâu hỏi hiện tại: {user_input}" if history else user_input
        llm_response = self.llm.generate_with_tools(
            prompt=tool_prompt, 
            tools=self.tools_schema, 
            system_prompt=self.system_prompt
        )
        timings["Trích xuất Tool"] = time.time() - t_start
        
        # 2. Thực thi các công cụ
        t_start = time.time()
        raw_db_data = self.execute_tools(llm_response)
        timings["Thực thi Tool"] = time.time() - t_start
        
        # 3. Tạo phản hồi cuối cùng
        t_start = time.time()
        context_payload = {
            "database_results": raw_db_data,
            "history": history
        }
        
        final_prompt = f"""
Câu hỏi của khách hàng: {user_input}
Dữ liệu từ hệ thống: {json.dumps(context_payload, indent=2, ensure_ascii=False)}

Hãy trả lời khách hàng dựa trên dữ liệu trên. Nếu không có dữ liệu, hãy báo không tìm thấy sản phẩm một cách lịch sự.
"""
        final_answer = self.llm.generate_text(prompt=final_prompt, system_prompt=self.system_prompt)
        timings["Tạo phản hồi"] = time.time() - t_start
        
        return {
            "text": final_answer,
            "raw_data": raw_db_data,
            "timings": timings
        }

    def handle_query_stream(self, user_input: str, history: str = ""):
        # 1. Tool Calls
        tool_prompt = f"Lịch sử hội thoại:\n{history}\n\nCâu hỏi hiện tại: {user_input}" if history else user_input
        llm_response = self.llm.generate_with_tools(
            prompt=tool_prompt, 
            tools=self.tools_schema, 
            system_prompt=self.system_prompt
        )
        raw_db_data = self.execute_tools(llm_response)
        
        # Trả về dữ liệu thô trước nếu có
        yield {"raw_data": raw_db_data, "text": "", "finish": False}
        
        # 2. Stream Answer
        context_payload = {"database_results": raw_db_data, "history": history}
        final_prompt = f"Câu hỏi: {user_input}\nDữ liệu: {json.dumps(context_payload, ensure_ascii=False)}"
        
        full_text = ""
        for chunk in self.llm.generate_stream(prompt=final_prompt, system_prompt=self.system_prompt):
            full_text += chunk
            yield {"text": full_text, "finish": False}
        
        yield {"text": full_text, "finish": True}

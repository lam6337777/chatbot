import json
import time
from Skills.Base_skill import BaseSkill
from MCP_Tools.Policy_tools import Policy_tools
from MCP_Tools.Promotion_tools import Promotion_tools

class PromotionSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="Promotion Skill",
            description="Thông tin về các chương trình khuyến mãi, sự kiện giảm giá và kiểm tra mã voucher.",
            prompt_filename="Promotion.txt"
        )
        self.policy_tools = Policy_tools()
        self.promotion_tools = Promotion_tools()
        
        self.tools_dict = {
            "get_active_promotions": self.promotion_tools.get_active_coupons, 
            "validate_voucher": lambda voucher_code, cart_total=0: self.promotion_tools.validate_coupon(voucher_code, cart_total), 
            "get_loyalty_info": lambda user_id="guest": self.policy_tools.get_policy("faq"),
        }

        self.tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "get_active_promotions",
                    "description": "Lấy danh sách tất cả các chương trình khuyến mãi đang diễn ra.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "validate_voucher",
                    "description": "Kiểm tra tính hợp lệ của mã voucher với giá trị đơn hàng.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "voucher_code": {"type": "string"},
                            "cart_total": {"type": "integer"}
                        },
                        "required": ["voucher_code"]
                    }
                }
            }
        ]

    def handle_query(self, user_input: str, history: str = "") -> dict:
        print(f" [{self.name}] Đang xử lý: {user_input}")
        timings = {}
        
        t_start = time.time()
        tool_prompt = f"Lịch sử hội thoại:\n{history}\n\nCâu hỏi hiện tại: {user_input}" if history else user_input
        llm_response = self.llm.generate_with_tools(
            prompt=tool_prompt, 
            tools=self.tools_schema, 
            system_prompt=self.system_prompt
        )
        timings["Trích xuất Tool"] = time.time() - t_start
        
        t_start = time.time()
        raw_db_data = self.execute_tools(llm_response)
        timings["Thực thi Tool"] = time.time() - t_start
        
        t_start = time.time()
        context_payload = {
            "promotion_results": raw_db_data,
            "history": history
        }
        
        final_prompt = f"""
Câu hỏi của khách hàng: {user_input}
Dữ liệu từ hệ thống: {json.dumps(context_payload, indent=2, ensure_ascii=False)}

Hãy tư vấn cho khách hàng về các ưu đãi hiện có hoặc giải thích về voucher họ đã cung cấp.
"""
        final_answer = self.llm.generate_text(prompt=final_prompt, system_prompt=self.system_prompt)
        timings["Tạo phản hồi"] = time.time() - t_start
        
        return {
            "text": final_answer,
            "raw_data": raw_db_data,
            "timings": timings
        }

    def handle_query_stream(self, user_input: str, history: str = ""):
        tool_prompt = f"Lịch sử hội thoại:\n{history}\n\nCâu hỏi hiện tại: {user_input}" if history else user_input
        llm_response = self.llm.generate_with_tools(
            prompt=tool_prompt, 
            tools=self.tools_schema, 
            system_prompt=self.system_prompt
        )
        raw_db_data = self.execute_tools(llm_response)
        yield {"raw_data": raw_db_data, "text": "", "finish": False}
        
        context_payload = {"promotion_results": raw_db_data, "history": history}
        final_prompt = f"Câu hỏi: {user_input}\nDữ liệu: {json.dumps(context_payload, ensure_ascii=False)}"
        
        full_text = ""
        for chunk in self.llm.generate_stream(prompt=final_prompt, system_prompt=self.system_prompt):
            full_text += chunk
            yield {"text": full_text, "finish": False}
        
        yield {"text": full_text, "finish": True}

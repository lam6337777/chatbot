import json
import time
from Skills.Base_skill import BaseSkill
from MCP_Tools.Order_tools import Order_tools
from MCP_Tools.Payment_tools import Payment_tools
from MCP_Tools.Warranty_tools import Warranty_tools
from MCP_Tools.Policy_tools import Policy_tools

class OrderSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="Order Skill",
            description="Quản lý đơn hàng, theo dõi trạng thái, hủy đơn, thanh toán và khiếu nại/đổi trả.",
            prompt_filename="Order.txt"
        )
        self.order_tools = Order_tools()
        self.payment_tools = Payment_tools()
        self.warranty_tools = Warranty_tools()
        self.policy_tools = Policy_tools()
        
        self.tools_dict = {
            "get_order_status": self.order_tools.get_order_status,
            "cancel_order": self.order_tools.cancel_order,
            "update_order_info": self.order_tools.modify_order,
            "check_return_eligibility": self.warranty_tools.check_return_eligibility,
            "submit_return_request": self.warranty_tools.submit_return_request,
            "get_shipping_fee": self.policy_tools.get_shipping_fee,
            "get_payment_status": self.payment_tools.get_payment_status,
            "get_return_request_status": self.order_tools.get_return_request_status,
        }

        self.tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "get_order_status",
                    "description": "Kiểm tra trạng thái hiện tại của đơn hàng qua mã đơn.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string"}
                        },
                        "required": ["order_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "cancel_order",
                    "description": "Thực hiện hủy một đơn hàng.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string"},
                            "reason": {"type": "string"}
                        },
                        "required": ["order_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_shipping_fee",
                    "description": "Tính toán phí vận chuyển dự kiến.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "province": {"type": "string"},
                            "district": {"type": "string"}
                        },
                        "required": ["province"]
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
            "database_results": raw_db_data,
            "history": history
        }
        
        final_prompt = f"""
Câu hỏi của khách hàng: {user_input}
Dữ liệu từ hệ thống: {json.dumps(context_payload, indent=2, ensure_ascii=False)}

Dựa trên dữ liệu trên, hãy trả lời khách hàng về tình trạng đơn hàng hoặc chính sách liên quan.
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
        
        context_payload = {"database_results": raw_db_data, "history": history}
        final_prompt = f"Câu hỏi: {user_input}\nDữ liệu: {json.dumps(context_payload, ensure_ascii=False)}"
        
        full_text = ""
        for chunk in self.llm.generate_stream(prompt=final_prompt, system_prompt=self.system_prompt):
            full_text += chunk
            yield {"text": full_text, "finish": False}
        
        yield {"text": full_text, "finish": True}

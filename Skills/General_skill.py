import json
import time
from Skills.Base_skill import BaseSkill
from MCP_Tools.Policy_tools import Policy_tools

class GeneralSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="General Skill",
            description="Thông tin chung về cửa hàng, chính sách đổi trả, bảo hành, địa chỉ và hỗ trợ tài khoản.",
            prompt_filename="General.txt"
        )
        self.policy_tools = Policy_tools()
        
        self.tools_dict = {
            "get_return_policy": self.policy_tools.get_policy, 
            "reset_password": self.policy_tools.handle_account_request,
            "get_contact_info": lambda: self.policy_tools.get_policy("faq"),
        }

        self.tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "get_return_policy",
                    "description": "Lấy nội dung chi tiết của một chính sách cụ thể.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "policy_type": {
                                "type": "string",
                                "enum": ["warranty", "return", "shipping", "payment", "sales", "privacy", "faq"]
                            }
                        },
                        "required": ["policy_type"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_contact_info",
                    "description": "Lấy thông tin liên hệ và giờ làm việc của cửa hàng.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
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
            "policy_results": raw_db_data,
            "history": history
        }
        
        final_prompt = f"""
Câu hỏi của khách hàng: {user_input}
Dữ liệu từ hệ thống: {json.dumps(context_payload, indent=2, ensure_ascii=False)}

Hãy cung cấp thông tin chính xác dựa trên các chính sách của cửa hàng.
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
        
        context_payload = {"policy_results": raw_db_data, "history": history}
        final_prompt = f"Câu hỏi: {user_input}\nDữ liệu: {json.dumps(context_payload, ensure_ascii=False)}"
        
        full_text = ""
        for chunk in self.llm.generate_stream(prompt=final_prompt, system_prompt=self.system_prompt):
            full_text += chunk
            yield {"text": full_text, "finish": False}
        
        yield {"text": full_text, "finish": True}

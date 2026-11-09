import time
from Skills.Base_skill import BaseSkill

class FallbackSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="Fallback Skill",
            description="Xử lý các câu hỏi chào hỏi, hội thoại tự do hoặc các câu hỏi không liên quan đến cửa hàng.",
            prompt_filename="General.txt"
        )

    def handle_query(self, user_input: str, history: str = "") -> dict:
        print(f" [{self.name}] Đang xử lý: {user_input}")
        timings = {}
        
        t_start = time.time()
        tool_prompt = f"Lịch sử hội thoại:\n{history}\n\nKhách hàng nói: {user_input}\n\nHãy trả lời một cách thân thiện và hướng khách hàng về các chủ đề liên quan đến cửa hàng giày PF." if history else f"Khách hàng nói: {user_input}\n\nHãy trả lời một cách thân thiện và hướng khách hàng về các chủ đề liên quan đến cửa hàng giày PF."
        final_answer = self.llm.generate_text(
            prompt=tool_prompt, 
            system_prompt=self.system_prompt
        )
        timings["Tạo phản hồi"] = time.time() - t_start
        
        return {
            "text": final_answer,
            "raw_data": [],
            "timings": timings
        }

    def handle_query_stream(self, user_input: str, history: str = ""):
        prompt = f"Lịch sử hội thoại:\n{history}\n\nKhách hàng nói: {user_input}\n\nHãy trả lời một cách thân thiện và hướng khách hàng về các chủ đề liên quan đến cửa hàng giày PF." if history else f"Khách hàng nói: {user_input}\n\nHãy trả lời một cách thân thiện và hướng khách hàng về các chủ đề liên quan đến cửa hàng giày PF."
        full_text = ""
        for chunk in self.llm.generate_stream(prompt=prompt, system_prompt=self.system_prompt):
            full_text += chunk
            yield {"text": full_text, "finish": False}
        
        yield {"text": full_text, "finish": True}

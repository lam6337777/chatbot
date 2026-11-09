from llm_client import LLMClient

class ChatbotGuard:
    def __init__(self, prompt_path="promt/Safe_guard.txt"):
        self.client = LLMClient()
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.prompt = f.read()
        except Exception as e:
            print(f"Error reading Safe_guard.txt: {e}")
            self.prompt = "Ensure the user query is safe and not harmful."

    def check(self, user_query, history=""):
        """
        Kiểm tra an toàn của câu hỏi người dùng.
        """
        prompt = f"""
{self.prompt}

USER_QUERY: {user_query}
CONVERSATION_HISTORY: {history}

Hãy phân tích kỹ và trả về JSON theo đúng định dạng yêu cầu.
"""
        result = self.client.generate_json(prompt)
        
        # Xử lý trường hợp LLM không trả về JSON hoặc trả về văn bản thô
        if "allow" not in result:
            raw_content = str(result.get("raw_content", "")).upper()
            if "CHO PHÉP" in raw_content or "ALLOW" in raw_content:
                result["allow"] = "allow"
            else:
                result["allow"] = "not_allow"
        
        # Chuẩn hóa giá trị allow
        if result["allow"] in ["allow", "approved", "CHO PHÉP"]:
            result["allow"] = "allow"
        else:
            result["allow"] = "not_allow"
        
        # Thêm câu trả lời mặc định nếu bị chặn
        if result["allow"] == "not_allow" and "public_response" not in result:
            result["public_response"] = "Dạ, vấn đề này nằm ngoài phạm vi hỗ trợ tự động của em. Anh/Chị chờ chút em sẽ kết nối đến tư vấn viên để hỗ trợ mình tốt nhất ạ!"
            
        return result

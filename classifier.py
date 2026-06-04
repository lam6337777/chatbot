from llm_client import LLMClient

class ChatbotClassifier:
    def __init__(self, prompt_path="promt/Classification.txt"):
        self.client = LLMClient()
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.base_prompt = f.read()
        except Exception as e:
            print(f"Error reading Classification.txt: {e}")
            self.base_prompt = "Phân loại ý định của người dùng vào các danh mục phù hợp."

    def classify(self, query: str, skills_info: str = "", history: str = "") -> dict:
        """
        Phân loại ý định người dùng bằng LLM.
        """
        prompt = f"""
{self.base_prompt}

DANH SÁCH CÁC KỸ NĂNG CÓ SẴN:
{skills_info}

CURRENT_QUERY: {query}
CONVERSATION_HISTORY: {history}

Hãy trả về JSON với trường "class" là tên định danh của kỹ năng (ví dụ: product_related, order_related, ...) và "reasoning".
"""
        return self.client.generate_json(prompt)

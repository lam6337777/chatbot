import time
from llm_client import LLMClient

class Fallback_agent:
    """Agent for handling out-of-scope queries, pure greetings, and general chitchat."""
    def __init__(self):
        self.llm = LLMClient()
        try:
            # We can use General.txt or a specific Fallback.txt if available
            with open("promt/General.txt", "r", encoding="utf-8") as f:
                self.prompt = f.read()
        except Exception as e:
            print(f"Error reading General.txt: {str(e)}")
            self.prompt = "You are a polite assistant for PF shoe store. If the user query is unrelated to PF, politely explain that you can only help with PF-related topics (products, orders, policies)."

    def handle_query(self, user_input):
        print(f"[Fallback_agent] Processing: {user_input}")
        timings = {}
        
        # Simple text generation for fallback
        t_gen_start = time.time()
        text = self.llm.generate_text(f"{self.prompt}\n\nUser: {user_input}\n\nAssistant:")
        timings["Response Generation"] = time.time() - t_gen_start
        
        return {
            "text": text,
            "tool_calls": [],
            "raw_db_data": [],
            "timings": timings,
            "raw_response": None
        }

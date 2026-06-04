import os
import time
import json
from abc import ABC, abstractmethod
from llm_client import LLMClient

class BaseSkill(ABC):
    """
    Lớp cơ sở cho tất cả các kỹ năng (Skills) của Chatbot.
    Mỗi Skill tập trung vào một lĩnh vực cụ thể (Sản phẩm, Đơn hàng, Khuyến mãi...).
    """
    def __init__(self, name: str, description: str, prompt_filename: str):
        self.name = name
        self.description = description
        self.llm = LLMClient()
        self.tools_dict = {}
        self.tools_schema = []
        
        # Load prompt từ thư mục promt/
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(base_path, "promt", prompt_filename)
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
            print(f" [{self.name}] Đã tải prompt từ {prompt_filename}")
        except Exception as e:
            print(f" [!] Lỗi khi đọc {prompt_filename}: {str(e)}")
            self.system_prompt = f"Bạn là một chuyên gia về {self.name}."

    @abstractmethod
    def handle_query(self, user_input: str, history: str = "") -> dict:
        """Phương thức chính để xử lý yêu cầu của người dùng."""
        pass

    @abstractmethod
    def handle_query_stream(self, user_input: str, history: str = ""):
        """Phương thức hỗ trợ phản hồi theo luồng (streaming)."""
        pass

    def execute_tools(self, llm_response: dict) -> list:
        """Thực thi các công cụ dựa trên phản hồi từ LLM."""
        raw_results = []
        if llm_response.get("type") == "tool_calls":
            for call in llm_response["calls"]:
                func_name = call["name"]
                args = call["arguments"]
                
                # Làm sạch arguments
                if isinstance(args, dict):
                    args = {k: v for k, v in args.items() if v is not None and v != ""}
                
                print(f" -> Thực thi công cụ: {func_name} với {args}")
                
                if func_name in self.tools_dict:
                    try:
                        result = self.tools_dict[func_name](**args)
                        raw_results.append({
                            "tool": func_name,
                            "result": json.loads(result) if isinstance(result, str) else result
                        })
                    except Exception as e:
                        print(f"   [Lỗi] Thực thi {func_name} thất bại: {e}")
                        raw_results.append({"tool": func_name, "error": str(e)})
        return raw_results

import os
import json
import logging
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLMClient:
    """
    Unified LLM Client supporting MegaLLM and Ollama.
    Supports JSON mode, text generation, and Tool calling.
    """
    def __init__(self, model_name: str = None):
        self.use_ollama = os.environ.get("USE_OLLAMA", "false").lower() == "true"
        
        if self.use_ollama:
            self.backend_name = "Ollama (Local)"
            self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
            self.api_key = "ollama"
            self.model = model_name or os.environ.get("OLLAMA_MODEL", "gemma2:2b")
        else:
            self.backend_name = "Cloud LLM"
            # Cấu hình cho OpenAI / DeepSeek / Vercel Endpoint
            self.api_key = os.environ.get("LLM_API_KEY") or os.environ.get("MEGALLM_API_KEY")
            self.base_url = os.environ.get("LLM_BASE_URL", "https://ai.megallm.io/v1")
            self.model = model_name or os.environ.get("LLM_MODEL") or os.environ.get("MODEL", "deepseek-chat")
        
        logger.info(f"Using {self.backend_name}: {self.model} at {self.base_url}")
        
        # Các tham số sampling mặc định
        self.default_max_tokens = int(os.environ.get("LLM_MAX_TOKENS", 512))
        self.default_temperature = float(os.environ.get("LLM_TEMPERATURE", 0.7))
        self.default_top_p = float(os.environ.get("LLM_TOP_P", 0.9))
        
        logger.info(f"LLM Config: max_tokens={self.default_max_tokens}, temperature={self.default_temperature}, top_p={self.default_top_p}")

        if not self.api_key and not self.use_ollama:
            logger.error("MEGALLM_API_KEY not found in environment variables. LLM calls will fail.")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def generate_json(self, prompt: str, system_prompt: str = None, temperature: float = None, max_tokens: int = None, top_p: float = None) -> dict:
        """Gửi yêu cầu và đảm bảo phản hồi JSON với cơ chế parse linh hoạt."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else 0.0, # Chế độ JSON thường cần temp thấp
                response_format={"type": "json_object"},
                max_tokens=max_tokens if max_tokens is not None else self.default_max_tokens,
                top_p=top_p if top_p is not None else self.default_top_p
            )
            raw_content = response.choices[0].message.content
            
            try:
                return json.loads(raw_content)
            except json.JSONDecodeError:
                pass
            
            match = re.search(r'(\{.*\})', raw_content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            
            logger.error(f"JSON Parsing failed for content: {raw_content[:200]}...")
            return {"error": "JSON parse failed", "raw_content": raw_content}

        except Exception as e:
            logger.error(f"LLM generate_json Error: {e}")
            return {"error": str(e)}

    def generate_text(self, prompt: str, system_prompt: str = None, temperature: float = None, max_tokens: int = None, top_p: float = None) -> str:
        """Tạo phản hồi văn bản thuần túy."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else self.default_temperature,
                max_tokens=max_tokens if max_tokens is not None else self.default_max_tokens,
                top_p=top_p if top_p is not None else self.default_top_p
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM generate_text Error: {e}")
            return f"Error: {str(e)}"

    def generate_stream(self, prompt: str, system_prompt: str = None, temperature: float = None, max_tokens: int = None, top_p: float = None):
        """Tạo văn bản ở chế độ streaming (thời gian thực)."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else self.default_temperature,
                max_tokens=max_tokens if max_tokens is not None else self.default_max_tokens,
                top_p=top_p if top_p is not None else self.default_top_p,
                stream=True
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"LLM generate_stream Error: {e}")
            yield f"Error: {str(e)}"

    def generate_with_tools(self, prompt: str, tools: list, system_prompt: str = None, temperature: float = 0.1) -> dict:
        """Sử dụng LLM để phân tích intent và trả về gọi hàm (Tool Calling)."""
        
        # Nếu dùng Ollama mà model không hỗ trợ native tools, ta dùng prompt-based
        if self.use_ollama:
            return self._generate_with_tools_manual(prompt, tools, system_prompt, temperature)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature
            )
            msg = response.choices[0].message
            if msg.tool_calls:
                calls = []
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except Exception:
                        args = {}
                    calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": args
                    })
                return {"type": "tool_calls", "calls": calls}
            else:
                return {"type": "text", "content": msg.content or ""}
        except Exception as e:
            logger.info(f"LLM generate_with_tools Native tools Error: {e}. Falling back to manual.")
            return self._generate_with_tools_manual(prompt, tools, system_prompt, temperature)

    def _generate_with_tools_manual(self, prompt: str, tools: list, system_prompt: str = None, temperature: float = 0.1) -> dict:
        """Cơ chế gọi tool bằng prompt JSON (Dành cho model không hỗ trợ native tools)."""
        tools_desc = ""
        for t in tools:
            func = t.get("function", {})
            props = func.get('parameters', {}).get('properties', {})
            params_list = []
            for k, v in props.items():
                params_list.append(f"{k} ({v.get('type')})")
            params_str = ", ".join(params_list)
            tools_desc += f"- {func.get('name')}: {func.get('description')}\n  Tham số: {params_str}\n"

        manual_system_prompt = f"""
{system_prompt or "You are a helpful assistant."}

Dưới đây là danh sách công cụ bạn có thể sử dụng:
{tools_desc}

Nếu cần dùng công cụ, hãy trả về JSON:
{{
  "type": "tool_calls",
  "calls": [
    {{
      "name": "tên_công_cụ",
      "arguments": {{ "tham_số": "giá_trị_thực_tế" }}
    }}
  ]
}}

Nếu không cần công cụ, trả về JSON:
{{
  "type": "text",
  "content": "Câu trả lời trực tiếp của bạn"
}}

CHỈ TRẢ VỀ JSON.
"""
        try:
            res_json = self.generate_json(prompt, system_prompt=manual_system_prompt, temperature=temperature)
            if isinstance(res_json, dict) and "type" in res_json:
                return res_json
            return {"type": "text", "content": str(res_json)}
        except Exception as e:
            logger.error(f"LLM _generate_with_tools_manual Error: {e}")
            return {"type": "error", "error": str(e)}

# Singleton instances for global use
llm_client = LLMClient()
mega_llm_client = llm_client # Compatibility

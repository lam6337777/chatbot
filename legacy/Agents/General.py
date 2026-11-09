import json
import time
import os
from llm_client import LLMClient
from MCP_Tools.Policy_tools import Policy_tools

class General_agent:
    """Agent specialized in general store information, policies, privacy, account management, and FAQs."""
    def __init__(self):
        self.llm = LLMClient()
        self.policy_tools = Policy_tools()
        
        # Tools aligned 1:1 with promt/General.txt
        self.tools_dict = {
            "get_return_policy": self.policy_tools.get_policy, 
            "reset_password": self.policy_tools.handle_account_request,
            "get_contact_info": lambda: self.policy_tools.get_policy("faq"),
        }

        # JSON Schema for OpenAI Function Calling
        self.tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "get_return_policy",
                    "description": "Get raw content of a specific policy type.",
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
                    "name": "reset_password",
                    "description": "Process account-related requests specifically reset password.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"}
                        },
                        "required": ["user_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_contact_info",
                    "description": "Get customer support contact details and working hours.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
        ]

        # Safe prompt loading
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(base_path, "promt", "General.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.prompt = f.read()
            print(f" [General_agent] Successfully loaded prompt from {prompt_path}")
        except Exception as e:
            print(f"Error reading General.txt: {str(e)}")
            self.prompt = "You are an Info Expert for PF shoe store. Use tools to handle general queries."

    def handle_query(self, user_input):
        print(f"\n[General_agent] Processing Query: {user_input}")
        timings = {}
        
        # 1. LLM Extracts parameters and decides which tool(s) to call
        print(" [General_agent] Requesting tool calls from LLM...")
        t_extract_start = time.time()
        llm_response = self.llm.generate_with_tools(
            prompt=user_input, 
            tools=self.tools_schema, 
            system_prompt=self.prompt
        )
        timings["Tool Extraction"] = time.time() - t_extract_start
        
        raw_db_data = []
        action_logs = []
        
        # 2. Execute tools to fetch RAW DATA from DB
        t_exec_start = time.time()
        if llm_response.get("type") == "tool_calls":
            for call in llm_response["calls"]:
                func_name = call["name"]
                args = call["arguments"]
                print(f" -> Calling Tool: {func_name} with args: {args}")
                action_logs.append(f"Action: {func_name}({args})")
                
                if func_name in self.tools_dict:
                    try:
                        result = self.tools_dict[func_name](**args)
                        raw_db_data.append({
                            "tool": func_name,
                            "result": json.loads(result) if isinstance(result, str) else result
                        })
                    except Exception as e:
                        print(f"   [Error] Tool execution failed: {e}")
                        raw_db_data.append({"tool": func_name, "error": str(e)})
        else:
            print(" -> LLM decoded no tool calls needed for this query.")
        timings["Tool Execution"] = time.time() - t_exec_start
        
        # 3. Compile DB payload and Static Context
        static_context = "System Info: Use tools to check exact policies when users ask about rules."
 
        context_payload = {
            "database_query_results": raw_db_data,
            "static_company_info": static_context
        }
 
        # 4. Final Response Generation (Direct LLM)
        print(" [General_agent] Generating final answer using tool results...")
        t_gen_start = time.time()
        final_prompt = f"""
Câu hỏi của người dùng: {user_input}
 
Dưới đây là thông tin chính sách/hỗ trợ từ hệ thống:
{json.dumps(context_payload, indent=2, ensure_ascii=False)}
 
Hãy dựa vào dữ liệu trên để trả lời người dùng một cách chuyên nghiệp và thân thiện. 
Nếu dữ liệu trống hoặc không tìm thấy, hãy thông báo lịch sự cho người dùng.
"""
        final_answer = self.llm.generate_text(prompt=final_prompt, system_prompt=self.prompt)
        timings["Response Generation"] = time.time() - t_gen_start
        
        return {
            "text": final_answer,
            "tool_calls": action_logs,
            "raw_db_data": raw_db_data,
            "timings": timings
        }

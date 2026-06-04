import json
import time
import os
from llm_client import LLMClient
from MCP_Tools.Policy_tools import Policy_tools
from MCP_Tools.Promotion_tools import Promotion_tools

class Promotion_agent:
    """Agent specialized in sales events, discount codes, and vouchers."""
    def __init__(self):
        self.llm = LLMClient()
        self.policy_tools = Policy_tools()
        self.promotion_tools = Promotion_tools()
        
        # Tools aligned 1:1 with promt/Promotion.txt
        self.tools_dict = {
            "get_active_promotions": self.promotion_tools.get_active_coupons, 
            "validate_voucher": lambda voucher_code, cart_total=0: self.promotion_tools.validate_coupon(voucher_code, cart_total), 
            "get_loyalty_info": lambda user_id="guest": self.policy_tools.get_policy("faq"),
            "get_promotion_by_product": lambda pid: self.promotion_tools.get_active_coupons(),
        }

        # JSON Schema for OpenAI Function Calling
        self.tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "get_active_promotions",
                    "description": "Get all currently active promotions and sale events.",
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
                    "description": "Validate a discount voucher code against cart total.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "voucher_code": {"type": "string"},
                            "cart_total": {"type": "integer"}
                        },
                        "required": ["voucher_code"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_loyalty_info",
                    "description": "Get loyalty points balance and tier information for a user.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"}
                        },
                        "required": ["user_id"]
                    }
                }
            }
        ]

        # Safe prompt loading
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(base_path, "promt", "Promotion.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.prompt = f.read()
            print(f" [Promotion_agent] Successfully loaded prompt from {prompt_path}")
        except Exception as e:
            print(f"Error reading Promotion.txt: {str(e)}")
            self.prompt = "You are a Promotion Expert for PF shoe store. Use tools to handle offers and vouchers."

    def handle_query(self, user_input):
        print(f"\n[Promotion_agent] Processing Query: {user_input}")
        timings = {}
        
        # 1. LLM Extracts parameters and decides which tool to call
        print(" [Promotion_agent] Requesting tool calls from LLM...")
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
        static_context = "System Info: Use get_policy_summary tool if user asks for specific promo or sales policies."

        context_payload = {
            "database_query_results": raw_db_data,
            "static_company_info": static_context
        }

        # 4. Final Response Generation (Direct LLM)
        print(" [Promotion_agent] Generating final answer using tool results...")
        t_gen_start = time.time()
        
        final_prompt = f"""
Câu hỏi của người dùng: {user_input}

Dưới đây là thông tin khuyến mãi/vouchers từ hệ thống:
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

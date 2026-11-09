import json
import time
import os
from llm_client import LLMClient
from MCP_Tools.Order_tools import Order_tools
from MCP_Tools.Payment_tools import Payment_tools
from MCP_Tools.Warranty_tools import Warranty_tools
from MCP_Tools.Policy_tools import Policy_tools

class Order_agent:
    """Agent specialized in order management, status tracking, cancellations, payments, and order-related warranty/returns."""
    def __init__(self):
        self.llm = LLMClient()
        self.order_tools = Order_tools()
        self.payment_tools = Payment_tools()
        self.warranty_tools = Warranty_tools()
        self.policy_tools = Policy_tools()
        
        # Tools aligned 1:1 with promt/Order.txt
        self.tools_dict = {
            "get_order_status": self.order_tools.get_order_status,
            "cancel_order": self.order_tools.cancel_order,
            "update_order_info": self.order_tools.modify_order, # Map modify to update
            "check_return_eligibility": self.warranty_tools.check_return_eligibility,
            "submit_return_request": self.warranty_tools.submit_return_request,
            "get_shipping_fee": self.policy_tools.get_shipping_fee, # Match prompt name
            "get_payment_status": self.payment_tools.get_payment_status,
            "get_return_request_status": self.order_tools.get_return_request_status,
        }

        # JSON Schema for OpenAI Function Calling
        self.tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "get_order_status",
                    "description": "Check current status of an order using its ID.",
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
                    "description": "Attempt to cancel an order.",
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
                    "name": "update_order_info",
                    "description": "Modify shipping address or contact info for an unfulfilled order.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string"},
                            "new_address": {"type": "string"},
                            "new_phone": {"type": "string"}
                        },
                        "required": ["order_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_return_eligibility",
                    "description": "Check if an order is eligible for return/refund based on policy.",
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
                    "name": "submit_return_request",
                    "description": "Submit a new return request for an order.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string"},
                            "reason": {"type": "string"},
                            "images": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["order_id", "reason"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_shipping_fee",
                    "description": "Calculate estimated shipping fee.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "province": {"type": "string"},
                            "district": {"type": "string"},
                            "weight": {"type": "integer"}
                        },
                        "required": ["province"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_payment_status",
                    "description": "Check payment status of an order.",
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
                    "name": "get_return_request_status",
                    "description": "Check the status of a return or refund request for an order.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_code": {"type": "string"}
                        },
                        "required": ["order_code"]
                    }
                }
            }
        ]

        # Safe prompt loading
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(base_path, "promt", "Order.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.prompt = f.read()
            print(f" [Order_agent] Successfully loaded prompt from {prompt_path}")
        except Exception as e:
            print(f"Error reading Order.txt: {str(e)}")
            self.prompt = "You are an Order Management Expert for PF shoe store. Use tools to handle order queries."

    def handle_query(self, user_input):
        print(f"\n[Order_agent] Processing Query: {user_input}")
        timings = {}
        
        # 1. LLM Extracts parameters and decides which tool(s) to call
        print(" [Order_agent] Requesting tool calls from LLM...")
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
        static_context = "System Info: If asked about policies, remind user or use get_policy_summary tool if necessary."
 
        context_payload = {
            "database_query_results": raw_db_data,
            "static_company_info": static_context
        }
 
        # 4. Final Response Generation (Direct LLM)
        print(" [Order_agent] Generating final answer using tool results...")
        t_gen_start = time.time()
        final_prompt = f"""
Câu hỏi của người dùng: {user_input}
 
Dưới đây là thông tin từ hệ thống để trả lời câu hỏi:
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

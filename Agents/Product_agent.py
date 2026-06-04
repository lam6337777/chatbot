import json
import time
import os
from llm_client import LLMClient
from MCP_Tools.Product_tools import Product_tools

class Product_agent:
    """Agent specialized in product searches, stock checks, and size guides."""
    def __init__(self):
        self.llm = LLMClient()
        self.product_tools = Product_tools()
        from MCP_Tools.Policy_tools import Policy_tools
        self.policy_tools = Policy_tools()
        
        # Tools aligned 1:1 with promt/Product.txt
        self.tools_dict = {
            "search_products": self.product_tools.search_products,
            "get_product_details": self.product_tools.get_product_details,
            "check_availability": self.product_tools.check_availability,
            "get_new_arrivals": self.product_tools.get_new_arrivals,
            "get_similar_products": self.product_tools.get_similar_products,
            "get_product_reviews": self.product_tools.get_product_reviews,
            "get_top_rated_products": self.product_tools.get_top_rated_products,
            "get_product_by_name": self.product_tools.get_product_by_name,
        }

        # JSON Schema for OpenAI Function Calling
        self.tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "search_products",
                    "description": "Find products with filters: brand, category, size, color, price range.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "brand": {"type": "string"},
                            "category": {"type": "string"},
                            "size": {"type": "string"},
                            "color": {"type": "string"},
                            "min_price": {"type": "integer"},
                            "max_price": {"type": "integer"},
                            "in_stock_only": {"type": "boolean"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_product_details",
                    "description": "Get full details and variants for a specific product ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"}
                        },
                        "required": ["product_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_availability",
                    "description": "Check stock quantity for a specific product variant.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "size": {"type": "string"},
                            "color": {"type": "string"}
                        },
                        "required": ["product_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_new_arrivals",
                    "description": "Get the latest added products.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_similar_products",
                    "description": "Get products similar to the given product (same category).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "string"},
                            "limit": {"type": "integer"}
                        },
                        "required": ["product_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_product_reviews",
                    "description": "Get customer reviews and ratings for a specific product.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "string"}
                        },
                        "required": ["product_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_top_rated_products",
                    "description": "Get the highest-rated products in the store.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_product_by_name",
                    "description": "Get detailed information about a product by searching for its name.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"}
                        },
                        "required": ["name"]
                    }
                }
            }
        ]

        # Safe prompt loading
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(base_path, "promt", "Product.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.prompt = f.read()
            print(f" [Product_agent] Successfully loaded prompt from {prompt_path}")
        except Exception as e:
            print(f"Error reading Product.txt: {str(e)}")
            self.prompt = "You are a Product Expert for PF shoe store. Use tools to help customers find products."

    def handle_query(self, user_input):
        print(f"\n[Product_agent] Processing Query: {user_input}")
        timings = {}
        
        # 1. LLM Extracts parameters and decides which tool to call
        print(" [Product_agent] Requesting tool calls from LLM...")
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
                
                # Lọc các giá trị lỗi từ model nhỏ
                if isinstance(args, dict):
                    args = {k: v for k, v in args.items() 
                            if v is not None 
                            and v != "null" 
                            and v != "" 
                            and not (isinstance(v, dict) and 'type' in v)}
                print(f" -> Calling Tool: {func_name} with args: {args}")
                action_logs.append(f"Action: {func_name}({args})")
                
                if func_name in self.tools_dict:
                    try:
                        # Execute the actual python function and get DB json strings
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
        static_context = "System Info: Use tools to retrieve size guide or policies if requested."
                
        context_payload = {
            "database_query_results": raw_db_data,
            "static_company_info": static_context
        }
 
        # 4. Final Response Generation (Direct LLM)
        print(" [Product_agent] Generating final answer using tool results...")
        t_gen_start = time.time()
        final_prompt = f"""
Câu hỏi của người dùng: {user_input}

Dưới đây là dữ liệu từ cơ sở dữ liệu để trả lời câu hỏi:
{json.dumps(context_payload, indent=2, ensure_ascii=False)}

Hãy dựa vào dữ liệu trên để trả lời người dùng một cách chuyên nghiệp và thân thiện. 
QUAN TRỌNG: Nếu `database_query_results` trống hoặc báo lỗi không tìm thấy, TUYỆT ĐỐI KHÔNG tự bịa ra thông tin sản phẩm và KHÔNG hỏi lại kiểu "Bạn có muốn tôi cung cấp thêm không". 
Hãy trả lời dứt khoát: "Xin lỗi, hiện tại PF không tìm thấy thông tin sản phẩm hoặc sản phẩm này đã hết hàng. Bạn có muốn tham khảo mẫu giày khác không?"
"""
        final_answer = self.llm.generate_text(prompt=final_prompt, system_prompt=self.prompt)
        timings["Response Generation"] = time.time() - t_gen_start
        
        return {
            "text": final_answer,
            "tool_calls": action_logs,
            "raw_db_data": raw_db_data,
            "timings": timings
        }

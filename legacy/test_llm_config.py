import os
from llm_client import LLMClient

def test_config():
    client = LLMClient()
    print(f"Backend: {client.backend_name}")
    print(f"Base URL: {client.base_url}")
    print(f"Model: {client.model}")
    print(f"Max Tokens: {client.default_max_tokens}")
    print(f"Temperature: {client.default_temperature}")
    print(f"Top P: {client.default_top_p}")

if __name__ == "__main__":
    test_config()

import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from main import ChatbotOrchestrator
from typing import Optional, List

app = FastAPI(title="PF Shoe Chatbot API")

# Cấu hình CORS để Next.js (port 3000) có thể gọi
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Trong thực tế nên giới hạn port cụ thể
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Khởi tạo Orchestrator
orchestrator = ChatbotOrchestrator()

class ChatRequest(BaseModel):
    message: str
    history: Optional[str] = ""

class ChatResponse(BaseModel):
    text: str
    intent: str
    handoff: bool = False
    raw_data: Optional[List[dict]] = None

from fastapi.responses import StreamingResponse
import json
import asyncio

@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        response_data = orchestrator.handle_request_api(request.message, request.history)
        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/stream")
async def chat_stream(message: str, history: str = ""):
    """
    Endpoint hỗ trợ streaming response (SSE).
    """
    async def event_generator():
        try:
            # Sử dụng orchestrator để stream (cần bổ sung hàm này)
            for chunk in orchestrator.handle_request_stream(message, history):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01) # Tránh nghẽn
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/handoff")
async def handoff(request: ChatRequest):
    # Logic để thông báo cho hệ thống admin
    # Ví dụ: Lưu vào DB với status PENDING_ADMIN
    return {"status": "success", "message": "Đã gửi yêu cầu kết nối với tư vấn viên."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

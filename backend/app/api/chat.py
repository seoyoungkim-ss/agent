from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings
from app.services.llm_client import InternalLLMClient

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@router.post("/stream")
async def chat_stream(payload: ChatRequest):
    """PRD 8: Agent 채팅. SSE로 사내 LLM 응답을 스트리밍한다."""
    client = InternalLLMClient(get_settings())
    messages = [m.model_dump() for m in payload.messages]

    async def event_generator() -> AsyncIterator[str]:
        async for chunk in client.chat_stream(messages):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

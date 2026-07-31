from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services.chat_grounding import build_grounded_context
from app.services.llm_client import InternalLLMClient

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@router.post("/stream")
async def chat_stream(payload: ChatRequest, db: Session = Depends(get_db)):
    """PRD 8: Agent 채팅. SSE로 사내 LLM 응답을 스트리밍한다.

    InternalLLMClient는 tool calling을 지원하지 않으므로, 실제 데이터를
    근거로 답하게 하려면 질문을 미리 규칙 기반으로 분류해 관련 데이터를
    조회한 뒤 system 메시지로 주입해야 한다(2026-07, chat_grounding.py).
    """
    client = InternalLLMClient(get_settings())
    messages = [m.model_dump() for m in payload.messages]
    last_user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    grounded_context = build_grounded_context(db, last_user_message)
    messages = [{"role": "system", "content": grounded_context}, *messages]

    async def event_generator() -> AsyncIterator[str]:
        async for chunk in client.chat_stream(messages):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

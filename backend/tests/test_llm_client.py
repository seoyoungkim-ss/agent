import json

import httpx
import pytest

from app.config import Settings
from app.services import llm_client as llm_client_module
from app.services.llm_client import InternalLLMClient


_RealAsyncClient = httpx.AsyncClient


def _patch_async_client(monkeypatch, handler) -> None:
    def fake_async_client(*args, **kwargs):
        kwargs.pop("timeout", None)
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(llm_client_module.httpx, "AsyncClient", fake_async_client)


@pytest.mark.asyncio
async def test_chat_stream_posts_non_streaming_request_and_yields_words(monkeypatch):
    """사내 LLM 게이트웨이는 SSE 스트리밍이 아니라 requests.post()로 한 번에 전체
    응답(OpenAI 호환 choices[0].message.content 형식)을 받는 방식으로 확인됐다
    (2026-07) — stream:true를 안 보내고, 응답을 한 번에 받아 단어 단위로 yield
    하는지 검증한다."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "안녕 하세요"}}]})

    _patch_async_client(monkeypatch, handler)

    settings = Settings(
        internal_llm_base_url="https://internal-llm.example.com/v1",
        internal_llm_api_key="secret-key",
        internal_llm_chat_model="thinkingcap",
    )
    client = InternalLLMClient(settings)

    chunks = [c async for c in client.chat_stream([{"role": "user", "content": "안녕"}])]

    assert captured["url"] == "https://internal-llm.example.com/v1/chat/completions"
    assert captured["body"] == {"model": "thinkingcap", "messages": [{"role": "user", "content": "안녕"}]}
    assert "stream" not in captured["body"]
    assert captured["auth"] == "Bearer secret-key"
    assert "".join(chunks) == "안녕 하세요 "


def test_is_configured_does_not_require_api_key():
    """인증이 필요 없는 사내 API도 있어(2026-07 실사용 확인) base_url만 있어도
    설정된 것으로 간주해야 한다 — api_key를 필수로 요구하면 안 된다."""
    settings = Settings(internal_llm_base_url="https://internal-llm.example.com/v1", internal_llm_api_key="")
    assert InternalLLMClient(settings).is_configured is True


def test_is_configured_false_without_base_url():
    settings = Settings(internal_llm_base_url="", internal_llm_api_key="")
    assert InternalLLMClient(settings).is_configured is False


@pytest.mark.asyncio
async def test_chat_stream_omits_auth_header_when_api_key_not_set(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "응답"}}]})

    _patch_async_client(monkeypatch, handler)

    settings = Settings(internal_llm_base_url="https://internal-llm.example.com/v1", internal_llm_api_key="")
    client = InternalLLMClient(settings)

    [c async for c in client.chat_stream([{"role": "user", "content": "안녕"}])]

    assert captured["auth"] is None


@pytest.mark.asyncio
async def test_chat_complete_joins_words_from_non_streaming_response(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "결과 문장"}}]})

    _patch_async_client(monkeypatch, handler)

    settings = Settings(
        internal_llm_base_url="https://internal-llm.example.com/v1",
        internal_llm_api_key="secret-key",
    )
    client = InternalLLMClient(settings)

    result = await client.chat_complete([{"role": "user", "content": "질문"}])
    assert result.strip() == "결과 문장"

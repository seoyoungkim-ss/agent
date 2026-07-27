"""PRD 8: 사내 LLM API 연동 클라이언트.

실제 엔드포인트/스펙이 아직 확정되지 않았으므로(PRD 10 Open Questions), OpenAI
호환 chat-completions 스트리밍 형식을 기본 가정으로 구현하고, 엔드포인트가
설정되지 않은 경우(로컬 개발/데모)에는 명확히 표시된 모의(mock) 응답으로
대체한다. 실제 사내 LLM 스펙이 확정되면 이 클라이언트만 교체하면 된다.
"""

from collections.abc import AsyncIterator

import httpx

from app.config import Settings


class InternalLLMClient:
    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.internal_llm_base_url and self._settings.internal_llm_api_key)

    async def chat_stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        if not self.is_configured:
            async for chunk in self._mock_chat_stream(messages):
                yield chunk
            return

        url = f"{self._settings.internal_llm_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self._settings.internal_llm_api_key}"}
        body = {
            "model": self._settings.internal_llm_chat_model,
            "messages": messages,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    yield data

    async def chat_complete(self, messages: list[dict[str, str]]) -> str:
        """스트리밍이 필요 없는 짧은 호출(예: VOE 클러스터 라벨링)용 헬퍼."""
        chunks = [chunk async for chunk in self.chat_stream(messages)]
        return "".join(chunks)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.is_configured:
            return [self._mock_embedding(t) for t in texts]

        url = f"{self._settings.internal_llm_base_url.rstrip('/')}/embeddings"
        headers = {"Authorization": f"Bearer {self._settings.internal_llm_api_key}"}
        body = {"model": self._settings.internal_llm_embedding_model, "input": texts}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in data["data"]]

    async def _mock_chat_stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        reply = (
            "[사내 LLM 미설정 — 모의 응답] "
            f"'{last_user}' 에 대한 답변을 사내 LLM API 연동 후 실제로 제공할 수 있습니다. "
            "INTERNAL_LLM_BASE_URL / INTERNAL_LLM_API_KEY를 .env에 설정하세요."
        )
        for word in reply.split(" "):
            yield word + " "

    def _mock_embedding(self, text: str) -> list[float]:
        # 재현 가능한 더미 임베딩(해시 기반) — 실제 의미 유사도는 없음, 배선 검증용.
        import hashlib

        from app.services.food_vector import COMMENT_EMBEDDING_DIM

        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = [(digest[i % len(digest)] / 255.0) for i in range(COMMENT_EMBEDDING_DIM)]
        return values

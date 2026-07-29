"""PRD 8: 사내 LLM API 연동 클라이언트.

사내 LLM 게이트웨이 확인 결과(2026-07): OpenAI 호환 chat-completions **응답
형식**(`data["choices"][0]["message"]["content"]`)은 맞지만, 스트리밍(SSE)은
지원하지 않고 `requests.post()`로 한 번에 전체 응답을 받는 방식이다. 그래서
`chat_stream()`은 실제로는 스트리밍 요청을 보내지 않고 **한 번에 응답을 받은
뒤, 호출부(Agent 채팅 SSE 등)와의 호환을 위해 단어 단위로 잘라서 순차
`yield`**한다(엔드포인트가 설정되지 않은 경우의 모의 응답과 같은 방식).
엔드포인트가 설정되지 않은 경우(로컬 개발/데모)에는 명확히 표시된 모의(mock)
응답으로 대체한다.

**프록시 우회(2026-07 실사용 확인)**: 사내망에는 pip 설치 등을 위해
`HTTP_PROXY`/`HTTPS_PROXY` 환경변수가 걸려있는 경우가 있는데, httpx는 기본
(`trust_env=True`)으로 이 환경변수를 그대로 읽어 **모든** 요청을 그 프록시로
보낸다 — 인터넷행 트래픽용 프록시라 인트라넷 전용인 사내 LLM 게이트웨이는
거치지 못해 연결이 실패한다(스트리밍/인증 문제를 다 고쳐도 남아있던 "network
error"의 원인). 아래 두 호출 모두 `trust_env=False`로 이 환경변수를 무시하고
직접 접속한다.
"""

from collections.abc import AsyncIterator

import httpx

from app.config import Settings


class InternalLLMClient:
    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        # 인증이 필요 없는 사내 API도 있어(2026-07 실사용 확인) api_key는 필수로
        # 안 본다 — base_url만 있으면 연동된 것으로 간주.
        return bool(self._settings.internal_llm_base_url)

    def _auth_headers(self) -> dict[str, str]:
        if not self._settings.internal_llm_api_key:
            return {}
        return {"Authorization": f"Bearer {self._settings.internal_llm_api_key}"}

    async def chat_stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        if not self.is_configured:
            async for chunk in self._mock_chat_stream(messages):
                yield chunk
            return

        url = f"{self._settings.internal_llm_base_url.rstrip('/')}/chat/completions"
        headers = self._auth_headers()
        body = {
            "model": self._settings.internal_llm_chat_model,
            "messages": messages,
        }
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        for word in content.split(" "):
            yield word + " "

    async def chat_complete(self, messages: list[dict[str, str]]) -> str:
        """스트리밍이 필요 없는 짧은 호출(예: VOE 클러스터 라벨링)용 헬퍼."""
        chunks = [chunk async for chunk in self.chat_stream(messages)]
        return "".join(chunks)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.is_configured:
            return [self._mock_embedding(t) for t in texts]

        url = f"{self._settings.internal_llm_base_url.rstrip('/')}/embeddings"
        headers = self._auth_headers()
        body = {"model": self._settings.internal_llm_embedding_model, "input": texts}
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in data["data"]]

    async def _mock_chat_stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        reply = (
            "[사내 LLM 미설정 — 모의 응답] "
            f"'{last_user}' 에 대한 답변을 사내 LLM API 연동 후 실제로 제공할 수 있습니다. "
            "INTERNAL_LLM_BASE_URL을 .env에 설정하세요(인증이 필요하면 INTERNAL_LLM_API_KEY도)."
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

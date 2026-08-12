import datetime as dt

import httpx
import pytest

from app.config import Settings
from app.services import weather_client as weather_client_module
from app.services.weather_client import KmaWeatherClient

_RealAsyncClient = httpx.AsyncClient


def _patch_async_client(monkeypatch, handler, captured_kwargs: dict | None = None) -> None:
    def fake_async_client(*args, **kwargs):
        if captured_kwargs is not None:
            captured_kwargs.update(kwargs)
        kwargs.pop("timeout", None)
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(weather_client_module.httpx, "AsyncClient", fake_async_client)


def _configured_settings(**overrides) -> Settings:
    defaults = dict(
        kma_weather_base_url="https://apis.data.go.kr/1360000/AsosDalyInfoService",
        kma_weather_api_key="secret-key",
        kma_weather_station_id="119",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_is_configured_requires_base_url_api_key_and_station():
    assert KmaWeatherClient(_configured_settings()).is_configured is True
    assert KmaWeatherClient(_configured_settings(kma_weather_api_key="")).is_configured is False
    assert KmaWeatherClient(_configured_settings(kma_weather_station_id="")).is_configured is False
    assert KmaWeatherClient(_configured_settings(kma_weather_base_url="")).is_configured is False


@pytest.mark.asyncio
async def test_fetch_daily_range_returns_empty_without_http_call_when_unconfigured(monkeypatch):
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    _patch_async_client(monkeypatch, handler)

    client = KmaWeatherClient(_configured_settings(kma_weather_api_key=""))
    records = await client.fetch_daily_range(dt.date(2026, 8, 1), dt.date(2026, 8, 2))

    assert records == []
    assert called is False


@pytest.mark.asyncio
async def test_fetch_daily_range_parses_items_and_treats_blank_sumrn_as_no_rain(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "response": {
                    "body": {
                        "items": {
                            "item": [
                                {"tm": "2026-08-01", "sumRn": "12.5", "avgTa": "24.3"},
                                {"tm": "2026-08-02", "sumRn": "", "avgTa": "26.1"},
                            ]
                        }
                    }
                }
            },
        )

    _patch_async_client(monkeypatch, handler)

    client = KmaWeatherClient(_configured_settings())
    records = await client.fetch_daily_range(dt.date(2026, 8, 1), dt.date(2026, 8, 2))

    assert "serviceKey=secret-key" in captured["url"]
    assert len(records) == 2
    rainy, dry = records
    assert rainy.stat_date == dt.date(2026, 8, 1)
    assert rainy.precip_mm == 12.5
    assert rainy.had_rain is True
    assert dry.stat_date == dt.date(2026, 8, 2)
    assert dry.precip_mm is None
    assert dry.had_rain is False
    assert dry.avg_temp_c == 26.1


@pytest.mark.asyncio
async def test_fetch_daily_range_does_not_double_encode_already_encoded_service_key(monkeypatch):
    """공공데이터포털의 "인코딩" 키(퍼센트 인코딩 포함, 예: %2F)를 httpx params에
    그대로 넣으면 %가 %25로 다시 인코딩돼 인증이 깨진다(2026-08 실사용 확인).
    이미 인코딩된 키는 URL에 직접 붙여 그대로 전송돼야 한다."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"response": {"body": {"items": {"item": []}}}})

    _patch_async_client(monkeypatch, handler)

    encoded_key = "abc%2Fdef%2Bghi%3D%3D"
    client = KmaWeatherClient(_configured_settings(kma_weather_api_key=encoded_key))
    await client.fetch_daily_range(dt.date(2026, 8, 1), dt.date(2026, 8, 1))

    assert f"serviceKey={encoded_key}" in captured["url"]
    assert "%25" not in captured["url"]  # 이중 인코딩(%가 %25로) 안 됐는지 확인


@pytest.mark.asyncio
async def test_fetch_daily_range_lets_httpx_encode_plain_service_key(monkeypatch):
    """퍼센트 인코딩 패턴이 없는 "디코딩" 키는 기존처럼 httpx params가 인코딩한다."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"response": {"body": {"items": {"item": []}}}})

    _patch_async_client(monkeypatch, handler)

    client = KmaWeatherClient(_configured_settings(kma_weather_api_key="plainDecodedKey123+/="))
    await client.fetch_daily_range(dt.date(2026, 8, 1), dt.date(2026, 8, 1))

    # httpx가 +, /, = 등을 표준 인코딩한 결과가 URL에 반영돼야 한다.
    assert "serviceKey=plainDecodedKey123" in captured["url"]
    assert "%2B" in captured["url"] or "%2F" in captured["url"]


@pytest.mark.asyncio
async def test_fetch_daily_range_handles_single_item_returned_as_dict(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": {
                    "body": {"items": {"item": {"tm": "2026-08-01", "sumRn": "0.0", "avgTa": "25.0"}}}
                }
            },
        )

    _patch_async_client(monkeypatch, handler)

    client = KmaWeatherClient(_configured_settings())
    records = await client.fetch_daily_range(dt.date(2026, 8, 1), dt.date(2026, 8, 1))

    assert len(records) == 1
    assert records[0].had_rain is False  # sumRn=0.0은 강수량 0 — had_rain은 >0만 True


@pytest.mark.asyncio
async def test_fetch_daily_range_does_not_force_trust_env_false(monkeypatch):
    """llm_client.InternalLLMClient는 인트라넷 전용이라 trust_env=False로 사내
    프록시를 우회하지만, 이 API는 공인 인터넷 목적지라 반대로 프록시를 타야
    도달할 수 있어 trust_env를 강제로 끄면 안 된다."""
    captured_kwargs: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": {"body": {"items": {"item": []}}}})

    _patch_async_client(monkeypatch, handler, captured_kwargs)

    client = KmaWeatherClient(_configured_settings())
    await client.fetch_daily_range(dt.date(2026, 8, 1), dt.date(2026, 8, 1))

    assert captured_kwargs.get("trust_env") is not False


@pytest.mark.asyncio
async def test_fetch_daily_range_respects_kma_weather_trust_env_false(monkeypatch):
    """§73: 사내망에 따라 프록시를 타는 것 자체가 실패 원인인 경우도 확인돼
    kma_weather_trust_env=False면 llm_client.py와 같은 방식으로 프록시를
    완전히 무시해야 한다."""
    captured_kwargs: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": {"body": {"items": {"item": []}}}})

    _patch_async_client(monkeypatch, handler, captured_kwargs)

    client = KmaWeatherClient(_configured_settings(kma_weather_trust_env=False))
    await client.fetch_daily_range(dt.date(2026, 8, 1), dt.date(2026, 8, 1))

    assert captured_kwargs.get("trust_env") is False


@pytest.mark.asyncio
async def test_fetch_daily_range_uses_default_verify_when_ca_bundle_not_set(monkeypatch):
    captured_kwargs: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": {"body": {"items": {"item": []}}}})

    _patch_async_client(monkeypatch, handler, captured_kwargs)

    client = KmaWeatherClient(_configured_settings())
    await client.fetch_daily_range(dt.date(2026, 8, 1), dt.date(2026, 8, 1))

    assert captured_kwargs.get("verify") is True


@pytest.mark.asyncio
async def test_fetch_daily_range_passes_ca_bundle_path_to_verify(monkeypatch):
    """사내 프록시가 TLS를 가로채는 경우("unable to get local issuer certificate"
    실사용 확인, 2026-08) kma_weather_ca_bundle을 설정하면 그 경로를 httpx의
    verify로 넘겨 사내 루트 인증서를 추가로 신뢰해야 한다."""
    captured_kwargs: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": {"body": {"items": {"item": []}}}})

    _patch_async_client(monkeypatch, handler, captured_kwargs)

    client = KmaWeatherClient(_configured_settings(kma_weather_ca_bundle="/etc/ssl/certs/corp-ca.pem"))
    await client.fetch_daily_range(dt.date(2026, 8, 1), dt.date(2026, 8, 1))

    assert captured_kwargs.get("verify") == "/etc/ssl/certs/corp-ca.pem"

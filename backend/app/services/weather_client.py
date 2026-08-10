"""PRD 7.1: 기상청 ASOS 종관기상관측 일자료(data.go.kr) 연동 클라이언트.

과거 강수-식수 상관관계를 실측으로 검증하기 위한 과거 날씨 조회용이다(2026-08).
사용자가 요청한 "중기 날씨 api"(중기예보, 미래 4~10일)와는 다른 API임에
주의 — 여긴 과거 실측 일자료(getWthrDataList)만 다룬다.

**프록시 방향이 llm_client.py와 반대다**: 사내 LLM 게이트웨이(llm_client.py)는
인트라넷 전용이라 `trust_env=False`로 사내 HTTP_PROXY/HTTPS_PROXY를 우회해야
접속됐다. 이 API는 반대로 공인 인터넷(data.go.kr) 목적지라, 사내망에 인터넷
프록시가 걸려 있다면 오히려 그 프록시를 **타야** 도달할 수 있다 — 그래서
여기서는 `trust_env`를 기본값(True)으로 둔다.

⚠️ 이 세션은 outbound가 제한돼 있어 data.go.kr 실제 응답을 라이브로 확인하지
못했다 — 아래 필드명(`tm`/`sumRn`/`avgTa`)과 응답 봉투 구조는 훈련 지식 기반
추정이며, 배포 전 실제 키로 한 번 대조 확인이 필요하다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import httpx

from app.config import Settings


@dataclass(frozen=True)
class DailyWeatherRecord:
    stat_date: dt.date
    precip_mm: float | None
    avg_temp_c: float | None

    @property
    def had_rain(self) -> bool:
        return self.precip_mm is not None and self.precip_mm > 0


def _parse_float(raw: str | None) -> float | None:
    # ASOS 일자료는 결측/무강수를 빈 문자열로 준다("0"이 아님) — 그대로 None 처리.
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_item(item: dict) -> DailyWeatherRecord:
    return DailyWeatherRecord(
        stat_date=dt.date.fromisoformat(item["tm"]),
        precip_mm=_parse_float(item.get("sumRn")),
        avg_temp_c=_parse_float(item.get("avgTa")),
    )


class KmaWeatherClient:
    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        # 공공데이터포털 API는 인증이 필수라 llm_client.InternalLLMClient와 달리
        # api_key도 필수로 본다(사내 LLM은 무인증 배포 사례가 있어 base_url만 봤음).
        s = self._settings
        return bool(s.kma_weather_base_url and s.kma_weather_api_key and s.kma_weather_station_id)

    async def fetch_daily_range(self, start: dt.date, end: dt.date) -> list[DailyWeatherRecord]:
        """[start, end] 구간(포함)의 일자료를 가져온다. 미설정이면 호출 없이 빈 리스트."""
        if not self.is_configured:
            return []

        url = f"{self._settings.kma_weather_base_url.rstrip('/')}/getWthrDataList"
        params = {
            "serviceKey": self._settings.kma_weather_api_key,
            "pageNo": "1",
            "numOfRows": str((end - start).days + 1),
            "dataType": "JSON",
            "dataCd": "ASOS",
            "dateCd": "DAY",
            "startDt": start.strftime("%Y%m%d"),
            "endDt": end.strftime("%Y%m%d"),
            "stnIds": self._settings.kma_weather_station_id,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        if isinstance(items, dict):  # 결과가 1건이면 리스트가 아니라 dict로 오는 공공데이터포털 특유 케이스
            items = [items]
        return [_parse_item(item) for item in items]

"""PRD 7.1: 기상청 ASOS 종관기상관측 일자료(data.go.kr) 연동 클라이언트.

과거 강수-식수 상관관계를 실측으로 검증하기 위한 과거 날씨 조회용이다(2026-08).
사용자가 요청한 "중기 날씨 api"(중기예보, 미래 4~10일)와는 다른 API임에
주의 — 여긴 과거 실측 일자료(getWthrDataList)만 다룬다.

**프록시 방향이 llm_client.py와 반대다**: 사내 LLM 게이트웨이(llm_client.py)는
인트라넷 전용이라 `trust_env=False`로 사내 HTTP_PROXY/HTTPS_PROXY를 우회해야
접속됐다. 이 API는 반대로 공인 인터넷(data.go.kr) 목적지라, 사내망에 인터넷
프록시가 걸려 있다면 오히려 그 프록시를 **타야** 도달할 수 있다 — 그래서
여기서는 `trust_env`를 기본값(True)으로 둔다.

다만 이 방향 가정이 모든 사내망에 맞는 건 아니라는 게 확인됐다(2026-08,
§73) — 어떤 사내망에서는 반대로 프록시를 타는 것 자체가 접속 실패
원인이었다. 그래서 `trust_env`를 `Settings.kma_weather_trust_env`로
빼서, 그런 환경에서는 `.env`에서 `false`로 뒤집어 llm_client.py와 같은
방식으로 프록시를 완전히 무시할 수 있게 했다.

**TLS 검사 프록시 대응(2026-08 실사용 확인)**: 사내 방화벽을 연 뒤에도
`unable to get local issuer certificate` 에러가 났다 — 사내 프록시가 아웃바운드
HTTPS를 가로채(TLS 인터셉션) 자체 인증서로 다시 서명하는 경우 흔한 증상이다.
httpx는 기본으로 certifi 번들만 신뢰하고 OS 신뢰 저장소나 `SSL_CERT_FILE`
환경변수를 자동으로 보지 않으므로, OS에 사내 루트 인증서가 설치돼 있어도
그걸 안 쓴다. `kma_weather_ca_bundle`에 사내 루트 인증서(PEM) 경로를 지정하면
그 파일을 신뢰 목록에 추가로 사용한다 — 검증 자체를 끄는(`verify=False`)
안전하지 않은 방식 대신 이 방법을 쓴다.

**서비스키 이중 인코딩 대응(2026-08 실사용 확인)**: 공공데이터포털은 같은
API에 "일반 인증키(Encoding)"와 "일반 인증키(Decoding)" 두 종류를 발급한다.
Encoding 키는 이미 퍼센트 인코딩된 문자열(`%2F` 등 포함)인데, httpx의
`params=` 딕셔너리에 그대로 넣으면 httpx가 값을 다시 인코딩해 `%`가 `%25`로
깨진다(이중 인코딩) — 인증 실패의 흔한 원인이다. 아래에서 서비스키에 이미
퍼센트 인코딩 패턴이 있으면 URL에 직접 붙여 다시 인코딩되지 않게 하고,
없으면(Decoding 키) 기존처럼 `params`에 넣어 httpx가 인코딩하게 둔다 —
사용자가 어느 키를 넣었는지 몰라도 두 경우 다 안전하게 동작한다.

⚠️ 이 세션은 outbound가 제한돼 있어 data.go.kr 실제 응답을 라이브로 확인하지
못했다 — 아래 필드명(`tm`/`sumRn`/`avgTa`)과 응답 봉투 구조는 훈련 지식 기반
추정이며, 배포 전 실제 키로 한 번 대조 확인이 필요하다.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

import httpx

from app.config import Settings

_PERCENT_ENCODED_PATTERN = re.compile(r"%[0-9A-Fa-f]{2}")


@dataclass(frozen=True)
class DailyWeatherRecord:
    stat_date: dt.date
    precip_mm: float | None
    avg_temp_c: float | None
    # PRD 7.1 확장(2026-08, §71): 메뉴×날씨유형(폭설/폭염/한파) 랭킹에 필요 —
    # ASOS 일자료 응답에 이미 같이 오는 필드(dsnw/maxTa/minTa)라 새 API 호출
    # 없이 파싱만 추가한다. 이 세션은 실제 응답을 라이브로 확인 못 해 필드명이
    # 훈련 지식 기반 추정이라는 기존 캐비아트(모듈 docstring)가 이 세 필드에도
    # 그대로 적용된다 — 배포 전 실제 키로 한 번 대조 확인 필요.
    snow_cm: float | None
    max_temp_c: float | None
    min_temp_c: float | None

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
        snow_cm=_parse_float(item.get("dsnw")),
        max_temp_c=_parse_float(item.get("maxTa")),
        min_temp_c=_parse_float(item.get("minTa")),
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

        base_url = f"{self._settings.kma_weather_base_url.rstrip('/')}/getWthrDataList"
        params = {
            "pageNo": "1",
            "numOfRows": str((end - start).days + 1),
            "dataType": "JSON",
            "dataCd": "ASOS",
            "dateCd": "DAY",
            "startDt": start.strftime("%Y%m%d"),
            "endDt": end.strftime("%Y%m%d"),
            "stnIds": self._settings.kma_weather_station_id,
        }
        service_key = self._settings.kma_weather_api_key
        if _PERCENT_ENCODED_PATTERN.search(service_key):
            # 이미 인코딩된 키 — URL에 직접 붙여 httpx가 다시 인코딩하지 않게 한다.
            url = f"{base_url}?serviceKey={service_key}"
        else:
            # 디코딩 키 — httpx의 자동 인코딩에 맡긴다.
            url = base_url
            params = {"serviceKey": service_key, **params}
        # 사내 프록시가 TLS를 가로채는 경우 certifi 기본 신뢰 목록만으론 검증이
        # 안 된다 — kma_weather_ca_bundle이 설정돼 있으면 그 PEM 파일을 추가로
        # 신뢰한다(미설정이면 기본 검증 그대로).
        verify = self._settings.kma_weather_ca_bundle or True
        async with httpx.AsyncClient(
            timeout=30.0, verify=verify, trust_env=self._settings.kma_weather_trust_env
        ) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        if isinstance(items, dict):  # 결과가 1건이면 리스트가 아니라 dict로 오는 공공데이터포털 특유 케이스
            items = [items]
        return [_parse_item(item) for item in items]

"""PRD 7.1 확장(2026-08, §71): 날짜 단위 실측 날씨를 평상시/비/폭설/폭염/한파
다섯 유형 중 하나로 분류한다 — "메인메뉴가 날씨유형별로 얼마나 인기 있었나"
랭킹(§71)의 기반이 되는 순수 함수.

holidays.py의 관례와 동일하게 DB 접근 없는 순수 함수로 만들어 빠르게
단위 테스트한다.
"""

from __future__ import annotations

import enum

from app.config import Settings


class WeatherEvent(str, enum.Enum):
    NORMAL = "평상시"
    RAIN = "비"
    HEAVY_SNOW = "폭설"
    HEATWAVE = "폭염"
    COLDWAVE = "한파"


def classify_weather_event(
    *,
    precip_mm: float | None,
    snow_cm: float | None,
    max_temp_c: float | None,
    min_temp_c: float | None,
    settings: Settings,
) -> WeatherEvent:
    """하루치 실측값을 다섯 유형 중 하나로 분류한다(상호 배타적).

    우선순위: 폭설 → 폭염 → 한파 → 비 → 평상시. 폭설은 저온 강수라 한파
    조건과 겹칠 수 있어(예: -13℃ + 신적설 6cm인 날) 더 구체적인 신호인
    폭설을 먼저 본다. 폭염과 한파는 같은 날 동시에 성립할 수 없어 그 둘의
    순서는 결과에 영향이 없다.

    ⚠️ 임계값(`config.py`의 `heavy_snow_threshold_cm`/`heatwave_temp_c`/
    `coldwave_temp_c`)은 기상청 특보 기준을 참고한 기본값이며, 실사용 전
    담당자 확인이 필요하다 — 관측소 ID·ASOS 필드명(`weather_client.py`)과
    같은 톤의 캐비아트다.
    """
    if snow_cm is not None and snow_cm >= settings.heavy_snow_threshold_cm:
        return WeatherEvent.HEAVY_SNOW
    if max_temp_c is not None and max_temp_c >= settings.heatwave_temp_c:
        return WeatherEvent.HEATWAVE
    if min_temp_c is not None and min_temp_c <= settings.coldwave_temp_c:
        return WeatherEvent.COLDWAVE
    if precip_mm is not None and precip_mm > 0:
        return WeatherEvent.RAIN
    return WeatherEvent.NORMAL

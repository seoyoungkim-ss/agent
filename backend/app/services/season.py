"""PRD 7.1 확장(2026-08, §72): 달력 계절(봄/여름/가을/겨울) 분류.

담당자 요청("계절로 묶은것도") — "냉면은 여름에, 팥죽은 겨울에" 같은
계절 음식 패턴을 메인메뉴 랭킹으로 보기 위한 기반. 기상학적 계절 관례
(3~5월 봄, 6~8월 여름, 9~11월 가을, 12·1·2월 겨울)로 월만 보고
분류한다 — 연도는 무관하게 여러 해의 같은 계절을 하나로 묶는다(요청
의도와 일치). holidays.py와 같은 관례로 DB 접근 없는 순수 함수라 빠르게
단위 테스트할 수 있다.

날씨유형(weather_event.py)과 달리 "평상시" 같은 기본/예외 그룹이
없다 — 모든 날짜가 정확히 하나의 계절에 속한다.
"""

from __future__ import annotations

import datetime as dt
import enum


class Season(str, enum.Enum):
    SPRING = "봄"
    SUMMER = "여름"
    FALL = "가을"
    WINTER = "겨울"


_MONTH_TO_SEASON: dict[int, Season] = {
    3: Season.SPRING,
    4: Season.SPRING,
    5: Season.SPRING,
    6: Season.SUMMER,
    7: Season.SUMMER,
    8: Season.SUMMER,
    9: Season.FALL,
    10: Season.FALL,
    11: Season.FALL,
    12: Season.WINTER,
    1: Season.WINTER,
    2: Season.WINTER,
}


def classify_season(target_date: dt.date) -> Season:
    return _MONTH_TO_SEASON[target_date.month]

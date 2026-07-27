"""2025~2026년 국내 공휴일 시드 데이터 (PRD 3.2).

⚠️ 검증 필요: 신정/삼일절/근로자의날/어린이날/현충일/광복절/개천절/한글날/성탄절처럼
매년 날짜가 고정된 항목은 신뢰도가 높지만, 아래 항목은 음력 변환 및 대체공휴일
판단 규정(관공서의 공휴일에 관한 규정)에 따라 계산한 **추정치**이므로 실제 배포
전에 반드시 공공데이터포털 "특일 정보" API 또는 공식 캘린더로 재검증할 것:
  - 설날/추석 연휴 날짜 (음력 변환)
  - 부처님오신날 날짜 (음력 변환)
  - 위 항목들이 토/일과 겹쳐 발생하는 대체공휴일 날짜

이 파일은 최초 시딩용이며, holiday_calendar 테이블은 이후 관리자가 직접
행을 추가/수정해 보완할 수 있다.
"""

import datetime as dt

from app.models.enums import HolidayType

# (날짜, 유형, 이름, 비고)
HOLIDAY_SEED: list[tuple[dt.date, HolidayType, str, str | None]] = [
    # ---- 2025 ----
    (dt.date(2025, 1, 1), HolidayType.STATUTORY, "신정", None),
    (dt.date(2025, 1, 28), HolidayType.STATUTORY, "설날 연휴", "음력 변환 — 재검증 필요"),
    (dt.date(2025, 1, 29), HolidayType.STATUTORY, "설날", "음력 변환 — 재검증 필요"),
    (dt.date(2025, 1, 30), HolidayType.STATUTORY, "설날 연휴", "음력 변환 — 재검증 필요"),
    (dt.date(2025, 3, 1), HolidayType.STATUTORY, "삼일절", None),
    (dt.date(2025, 3, 3), HolidayType.SUBSTITUTE, "대체공휴일(삼일절, 3/1이 토요일)", None),
    (dt.date(2025, 5, 1), HolidayType.LABOR_DAY, "근로자의 날", "법정공휴일은 아니나 휴일로 분류(PRD 3.1)"),
    (dt.date(2025, 5, 5), HolidayType.STATUTORY, "어린이날·부처님오신날(겹침)", "부처님오신날 음력 변환 — 재검증 필요"),
    (dt.date(2025, 5, 6), HolidayType.SUBSTITUTE, "대체공휴일(어린이날·부처님오신날 겹침)", None),
    (dt.date(2025, 6, 6), HolidayType.STATUTORY, "현충일", None),
    (dt.date(2025, 8, 15), HolidayType.STATUTORY, "광복절", None),
    (dt.date(2025, 10, 3), HolidayType.STATUTORY, "개천절", None),
    (dt.date(2025, 10, 5), HolidayType.STATUTORY, "추석 연휴", "음력 변환 — 재검증 필요"),
    (dt.date(2025, 10, 6), HolidayType.STATUTORY, "추석", "음력 변환 — 재검증 필요"),
    (dt.date(2025, 10, 7), HolidayType.STATUTORY, "추석 연휴", "음력 변환 — 재검증 필요"),
    (dt.date(2025, 10, 8), HolidayType.SUBSTITUTE, "대체공휴일(추석, 연휴 첫날이 일요일)", None),
    (dt.date(2025, 10, 9), HolidayType.STATUTORY, "한글날", None),
    (dt.date(2025, 12, 25), HolidayType.STATUTORY, "성탄절", None),
    # ---- 2026 ----
    (dt.date(2026, 1, 1), HolidayType.STATUTORY, "신정", None),
    (dt.date(2026, 2, 16), HolidayType.STATUTORY, "설날 연휴", "음력 변환 — 재검증 필요"),
    (dt.date(2026, 2, 17), HolidayType.STATUTORY, "설날", "음력 변환 — 재검증 필요"),
    (dt.date(2026, 2, 18), HolidayType.STATUTORY, "설날 연휴", "음력 변환 — 재검증 필요"),
    (dt.date(2026, 3, 1), HolidayType.STATUTORY, "삼일절", None),
    (dt.date(2026, 3, 2), HolidayType.SUBSTITUTE, "대체공휴일(삼일절, 3/1이 일요일)", None),
    (dt.date(2026, 5, 1), HolidayType.LABOR_DAY, "근로자의 날", "법정공휴일은 아니나 휴일로 분류(PRD 3.1)"),
    (dt.date(2026, 5, 5), HolidayType.STATUTORY, "어린이날", None),
    (dt.date(2026, 5, 24), HolidayType.STATUTORY, "부처님오신날", "음력 변환 — 재검증 필요"),
    (dt.date(2026, 5, 25), HolidayType.SUBSTITUTE, "대체공휴일(부처님오신날, 5/24가 일요일)", "재검증 필요"),
    (dt.date(2026, 6, 6), HolidayType.STATUTORY, "현충일", "토요일과 겹치나 현충일은 대체공휴일 미적용"),
    (dt.date(2026, 8, 15), HolidayType.STATUTORY, "광복절", None),
    (dt.date(2026, 8, 17), HolidayType.SUBSTITUTE, "대체공휴일(광복절, 8/15가 토요일)", None),
    (dt.date(2026, 9, 24), HolidayType.STATUTORY, "추석 연휴", "음력 변환 — 재검증 필요"),
    (dt.date(2026, 9, 25), HolidayType.STATUTORY, "추석", "음력 변환 — 재검증 필요"),
    (dt.date(2026, 9, 26), HolidayType.STATUTORY, "추석 연휴", "음력 변환 — 재검증 필요"),
    (
        dt.date(2026, 9, 28),
        HolidayType.SUBSTITUTE,
        "대체공휴일(추석, 연휴 마지막날이 토요일)",
        "토요일 겹침에 대한 대체공휴일 적용 여부는 특히 재검증 필요",
    ),
    (dt.date(2026, 10, 3), HolidayType.STATUTORY, "개천절", None),
    (dt.date(2026, 10, 5), HolidayType.SUBSTITUTE, "대체공휴일(개천절, 10/3이 토요일)", None),
    (dt.date(2026, 10, 9), HolidayType.STATUTORY, "한글날", None),
    (dt.date(2026, 12, 25), HolidayType.STATUTORY, "성탄절", None),
]

import enum


class MealType(str, enum.Enum):
    BREAKFAST = "조식"
    LUNCH = "중식"
    DINNER = "석식"


class Division(str, enum.Enum):
    HEADQUARTERS = "본사"
    AFFILIATE = "계열사"
    OTHER = "기타"


class TasteScore(str, enum.Enum):
    """PRD 6.3.1: 맛남=5, 보통=3, 개선=1 (5점 만점 환산)."""

    NEEDS_IMPROVEMENT = "개선"
    NORMAL = "보통"
    DELICIOUS = "맛남"


TASTE_SCORE_POINTS: dict[TasteScore, int] = {
    TasteScore.DELICIOUS: 5,
    TasteScore.NORMAL: 3,
    TasteScore.NEEDS_IMPROVEMENT: 1,
}


class MenuRole(str, enum.Enum):
    MAIN = "메인"
    SIDE = "부찬"


class HolidayType(str, enum.Enum):
    """PRD 3.1: 근로자의 날/대체공휴일을 포함해 휴일로 분류."""

    STATUTORY = "법정공휴일"
    SUBSTITUTE = "대체공휴일"
    LABOR_DAY = "근로자의날"
    COMPANY_OFF = "회사자체휴무"


class MenuQuadrant(str, enum.Enum):
    """PRD 6.3.4: 인기메뉴/숨은강자/개선시급/퇴출후보."""

    POPULAR = "인기메뉴"
    HIDDEN_GEM = "숨은강자"
    NEEDS_IMPROVEMENT = "개선시급"
    REMOVAL_CANDIDATE = "퇴출후보"
    LOW_SAMPLE = "표본부족"

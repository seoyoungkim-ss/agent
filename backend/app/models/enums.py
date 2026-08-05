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
    # 건강가든은 식단표 엑셀에 아직 안 들어온다 — 담당자가 화면에서 텍스트로
    # 직접 입력한다(협의 결정, 2026-08: "대략 5개 종류 반복이라 텍스트 입력으로
    # 일단 하자"). 데이터가 정식 유입되면 ingestion-tool이 같은 role로 적재하면
    # 되고, 화면·중복 판정 로직은 그대로 쓸 수 있다.
    HEALTH_GARDEN = "건강가든"


class MenuRoleSource(str, enum.Enum):
    """PRD: weekly_menu_plan.menu_role(주찬/부찬)이 어떻게 정해졌는지 구분한다.

    FoodVectorSource와 동일한 3단계 패턴 — MANUAL로 표시된 행은 이후 LLM
    일괄 재분류 배치(app/services/weekly_menu_role_llm.py)가 건드리지 않는다.
    """

    RULE = "규칙기반"
    LLM = "LLM추정"
    MANUAL = "관리자수동"


class HolidayType(str, enum.Enum):
    """PRD 3.1: 근로자의 날/대체공휴일을 포함해 휴일로 분류."""

    STATUTORY = "법정공휴일"
    SUBSTITUTE = "대체공휴일"
    LABOR_DAY = "근로자의날"
    COMPANY_OFF = "회사자체휴무"


class FoodVectorSource(str, enum.Enum):
    """PRD 6.1: menu_master.food_vector가 어떻게 채워졌는지 구분한다.

    MANUAL로 표시된 메뉴는 이후 규칙/LLM 재태깅 배치가 건드리지 않는다
    (app/services/food_vector_tagging.py 참고).
    """

    RULE = "규칙기반"
    LLM = "LLM추정"
    MANUAL = "관리자수동"


class MenuQuadrant(str, enum.Enum):
    """PRD 6.3.4: 인기메뉴/숨은강자/개선시급/퇴출후보."""

    POPULAR = "인기메뉴"
    HIDDEN_GEM = "숨은강자"
    NEEDS_IMPROVEMENT = "개선시급"
    REMOVAL_CANDIDATE = "퇴출후보"
    LOW_SAMPLE = "표본부족"


class TrendDirection(str, enum.Enum):
    """PRD 6.3.3/6.3.4: 만족도/점유율 등 지표의 기간 간 상승·유지·하락 추세.

    menu_performance_stats.satisfaction_trend 컬럼에 저장되므로(2026-07)
    다른 DB 저장 enum과 같이 이 모듈에 둔다.
    """

    UP = "상승"
    FLAT = "유지"
    DOWN = "하락"

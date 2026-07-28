"""ingestion-tool 전용 경량 타입 정의.

backend/app의 SQLAlchemy 모델을 그대로 import하지 않는다 — ingestion-tool은
운영자 Windows PC에 독립 설치되는 별도 컴포넌트이므로(PRD 9.2), psycopg/pgvector 등
Linux 백엔드 의존성 없이 가볍게 유지한다. 문자열 값(조식/중식/석식 등)은
backend의 enum과 반드시 일치해야 JSON 페이로드가 호환된다.
"""

import datetime as dt
from dataclasses import dataclass
from enum import Enum


class MealType(str, Enum):
    BREAKFAST = "조식"
    LUNCH = "중식"
    DINNER = "석식"


# 취식기록(POS)은 "조식/중식/석식"을, 맛평가 리스트는 "아침/점심/저녁"을 쓰는 등
# 소스 파일마다 어휘가 다르다. 새로운 표기가 발견되면 여기에만 추가하면 된다.
MEAL_TYPE_ALIASES: dict[str, MealType] = {
    "조식": MealType.BREAKFAST,
    "아침": MealType.BREAKFAST,
    "중식": MealType.LUNCH,
    "점심": MealType.LUNCH,
    "석식": MealType.DINNER,
    "저녁": MealType.DINNER,
}


def normalize_meal_type(raw: str) -> MealType | None:
    return MEAL_TYPE_ALIASES.get(raw.strip())


class MenuRole(str, Enum):
    MAIN = "메인"
    SIDE = "부찬"


class TasteScore(str, Enum):
    NEEDS_IMPROVEMENT = "개선"
    NORMAL = "보통"
    DELICIOUS = "맛남"


@dataclass(frozen=True)
class ParsedMenuRow:
    """weekly_menu_plan 적재용 파싱 결과 1건 (PRD 4.1 weekly_menu_plan)."""

    plan_date: dt.date
    meal_type: MealType
    corner_name: str
    menu_name: str
    menu_role: MenuRole
    source_row_raw: str


@dataclass(frozen=True)
class ParsedMealTransactionRow:
    """식당취식정보(POS 결제 로그) 원본 1행. 실제 컬럼 25개 중 분석에 쓰는 것만 추린다."""

    eaten_at: dt.datetime
    department_name: str  # 부문명
    worksite_name: str  # 사업장명
    company_name: str  # 회사 (예: 지리산, 제일원)
    employee_id: str  # 사원번호
    company_type: str  # 회사구분 — 원문 그대로 보존(협력사/관계사/... 확정 전까지 enum화 안 함)
    caterer: str  # 급식업체
    restaurant: str  # 식당 (예: SAIT)
    corner_name: str  # 코너
    meal_type: MealType  # 식구분 → normalize_meal_type으로 정규화됨
    packaging: str  # 포장구분 (DINE_IN 등)
    menu_code_name: str  # 메뉴명 (내부 코드성, 예: "고슬고슬비빔1")
    menu_display_name: str  # 화면표시명(한글) — 맛평가의 메뉴명과 매칭 대상
    receipt_no: str  # 영수증번호
    status: str  # 구분 (정상 등)
    is_corrected: bool  # 정정여부(Y/N)


@dataclass(frozen=True)
class ParsedTasteEvalRow:
    """식당 평가 리스트 원본 1행."""

    eaten_date: dt.date  # 취식일자 — 시간 정보 없음
    knox_id: str
    meal_type: MealType
    taste_score: TasteScore
    menu_name: str
    comment: str | None


@dataclass(frozen=True)
class ParsedMealLogRow:
    """meal_log 적재용 최종 병합 결과 1건 (PRD 4.1 meal_log).

    merge.merge_transactions_with_taste()가 ParsedMealTransactionRow +
    ParsedTasteEvalRow를 합쳐서 만든다. 평가가 없는 취식은 taste_score/comment가
    None인 채로 그대로 남는다(평가율이 100%가 아니므로 정상).
    """

    eaten_at: dt.datetime
    employee_id: str
    meal_type: MealType
    corner_name: str
    menu_name: str | None
    taste_score: TasteScore | None
    comment: str | None

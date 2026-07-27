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
class ParsedMealLogRow:
    """meal_log 적재용 파싱 결과 1건 (PRD 4.1 meal_log)."""

    eaten_at: dt.datetime
    employee_id: str
    meal_type: MealType
    corner_name: str
    taste_score: TasteScore | None
    comment: str | None

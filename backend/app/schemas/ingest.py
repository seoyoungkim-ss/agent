import datetime as dt

from pydantic import BaseModel

from app.models.enums import MealType, MenuRole, TasteScore


class WeeklyMenuRowIn(BaseModel):
    plan_date: dt.date
    meal_type: MealType
    corner_name: str
    menu_name: str
    menu_role: MenuRole
    source_row_raw: str | None = None


class WeeklyMenuIngestRequest(BaseModel):
    rows: list[WeeklyMenuRowIn]


class MealLogRowIn(BaseModel):
    eaten_at: dt.datetime
    employee_id: str
    meal_type: MealType
    corner_name: str
    # ingestion-tool이 식당취식정보의 "화면표시명(한글)"을 넣어준다. 있으면 이 값으로
    # 직접 메뉴를 연결하고(신뢰도 높음), 없으면 기존 weekly_menu_plan MAIN 매칭으로
    # 폴백한다 (app/api/ingest.py 참고).
    menu_name: str | None = None
    taste_score: TasteScore | None = None
    comment: str | None = None


class MealLogIngestRequest(BaseModel):
    rows: list[MealLogRowIn]


class IngestResult(BaseModel):
    received: int
    inserted: int
    new_menus: int = 0
    new_corners: int = 0

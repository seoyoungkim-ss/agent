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
    taste_score: TasteScore | None = None
    comment: str | None = None


class MealLogIngestRequest(BaseModel):
    rows: list[MealLogRowIn]


class IngestResult(BaseModel):
    received: int
    inserted: int
    new_menus: int = 0
    new_corners: int = 0

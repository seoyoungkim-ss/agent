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
    # 같은 식단표를 다시 올릴 때 중복이 쌓이지 않게 한다. true면 payload에 등장하는
    # (plan_date, corner_id, meal_type) 슬롯의 기존 행을 먼저 지우고 넣는다.
    # 기본 false — 기존 호출부 동작을 바꾸지 않는다(2026-08, 원산지 파싱 수정 후
    # 재업로드가 필요해지면서 추가).
    replace_existing: bool = False


class MealLogRowIn(BaseModel):
    eaten_at: dt.datetime
    employee_id: str
    meal_type: MealType
    corner_name: str
    # ingestion-tool이 식당취식정보의 "화면표시명(한글)"을 넣어준다. 있으면 이 값으로
    # 직접 메뉴를 연결하고(신뢰도 높음), 없으면 기존 weekly_menu_plan MAIN 매칭으로
    # 폴백한다 (app/api/ingest.py 참고).
    menu_name: str | None = None
    # 식당취식정보의 "회사" 원문 (예: 삼성전자/삼성SDI/지리산). 본사/계열사/기타
    # 분류에 쓰인다 (app/services/company_classification.py).
    company_name: str | None = None
    taste_score: TasteScore | None = None
    comment: str | None = None


class MealLogIngestRequest(BaseModel):
    rows: list[MealLogRowIn]


class WeatherRowIn(BaseModel):
    stat_date: dt.date
    precip_mm: float | None = None
    avg_temp_c: float | None = None
    # §71: 메뉴×날씨유형(폭설/폭염/한파) 랭킹용 — CSV에 없으면 None(하위호환).
    snow_cm: float | None = None
    max_temp_c: float | None = None
    min_temp_c: float | None = None


class WeatherCsvIngestRequest(BaseModel):
    # 사내망이 data.go.kr에 못 닿는 배포를 위한 대체 경로(PRD 7.1, 2026-08) —
    # scripts/import_weather_csv.py가 CSV를 읽어 이 형태로 올린다.
    rows: list[WeatherRowIn]


class WeatherIngestResult(BaseModel):
    received: int
    upserted: int


class IngestResult(BaseModel):
    received: int
    inserted: int
    new_menus: int = 0
    new_corners: int = 0
    # 관리자가 화면에서 고친 행이 이미 있어서 파서 결과를 안 넣은 건수.
    # 0이 아니면 "재업로드했는데 왜 그대로지?"의 답이 이것이다.
    skipped_manual: int = 0
    # payload 안에서 같은 (슬롯, 메뉴, 역할)이 두 번 온 건수 — 식단표 원본에
    # 같은 항목이 중복으로 적힌 경우.
    skipped_duplicate: int = 0

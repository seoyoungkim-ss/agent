from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_ingest_token
from app.db import get_db
from app.models.enums import MenuRole, MenuRoleSource
from app.models.logs import MealLog, WeeklyMenuPlan
from app.models.stats import DailyWeather
from app.schemas.ingest import (
    IngestResult,
    MealLogIngestRequest,
    WeatherCsvIngestRequest,
    WeatherIngestResult,
    WeeklyMenuIngestRequest,
)
from app.services.master_data import get_or_create_corner, get_or_create_employee, get_or_create_menu

router = APIRouter(prefix="/ingest", tags=["ingest"], dependencies=[Depends(require_ingest_token)])


@router.post("/weekly-menu", response_model=IngestResult)
def ingest_weekly_menu(payload: WeeklyMenuIngestRequest, db: Session = Depends(get_db)) -> IngestResult:
    new_corners = 0
    new_menus = 0
    inserted = 0
    replaced = 0
    skipped_manual = 0
    skipped_duplicate = 0

    # 코너는 여기서 한 번만 해석한다. 여러 루프에서 get_or_create를 다시 부르면
    # "새로 만들었나" 플래그를 두 번째 호출이 삼켜 new_corners가 0이 된다.
    corner_ids: dict[str, int] = {}
    for row in payload.rows:
        if row.corner_name not in corner_ids:
            corner, is_new_corner = get_or_create_corner(db, row.corner_name)
            if is_new_corner:
                new_corners += 1
            corner_ids[row.corner_name] = corner.corner_id

    # payload가 건드리는 슬롯들 — 교체 대상이자, 이미 있는 행을 찾는 범위.
    touched_slots = {
        (row.plan_date, corner_ids[row.corner_name], row.meal_type) for row in payload.rows
    }

    # 관리자가 손으로 고쳐 살아남을 행들의 (슬롯, 메뉴). 아래 삽입 루프가 이걸
    # 보고 같은 메뉴를 다시 넣지 않는다 — 2026-08 중복 사고의 핵심 수정.
    manual_keys: set[tuple] = set()

    if payload.replace_existing:
        # 슬롯 단위로 통째 교체한다. 이걸 안 하면 같은 파일을 다시 올릴 때
        # 행이 그대로 쌓여 편성 횟수·중복 판정이 전부 2배가 된다(dedup 없는 append).
        #
        # 단 role_source가 MANUAL인 행(관리자가 화면에서 직접 고친 주찬/부찬,
        # 건강가든 수기 입력)은 **교체 대상에서 제외**한다 — 사람이 손으로 넣은
        # 값이 재업로드로 조용히 날아가면 안 된다.
        #
        # ⚠️ 그런데 지우지 않는 것만으로는 부족했다. 예전 구현은 MANUAL 행을
        # 남겨두고 **payload를 통째로 다시 넣어서**, 관리자가 손댄 메뉴가 슬롯에
        # 두 벌씩 생겼다("부찬이 두번씩 들어갔다" 실사용 신고, 2026-08).
        # set_main_menu는 메인을 하나 지정할 때 같은 슬롯의 다른 MAIN들을 전부
        # SIDE로 내리면서 MANUAL로 찍으므로(weekly_menu_review.py:151-153),
        # 메인 하나만 고쳐도 부찬 여러 개가 이 경로를 탔다.
        for plan_date, corner_id, meal_type in touched_slots:
            replaced += (
                db.query(WeeklyMenuPlan)
                .filter(
                    WeeklyMenuPlan.plan_date == plan_date,
                    WeeklyMenuPlan.corner_id == corner_id,
                    WeeklyMenuPlan.meal_type == meal_type,
                    WeeklyMenuPlan.role_source != MenuRoleSource.MANUAL,
                )
                .delete(synchronize_session=False)
            )
            for (survivor_menu_id,) in db.query(WeeklyMenuPlan.menu_id).filter(
                WeeklyMenuPlan.plan_date == plan_date,
                WeeklyMenuPlan.corner_id == corner_id,
                WeeklyMenuPlan.meal_type == meal_type,
            ):
                manual_keys.add((plan_date, corner_id, meal_type, survivor_menu_id))

    # 같은 셀에 같은 부찬이 두 번 적힌 식단표가 있으면 그대로 두 행이 됐다.
    # 유니크 인덱스(uq_weekly_menu_plan_slot_menu_role)가 걸려 있으므로 여기서
    # 걸러내지 않으면 정상 입력이 500으로 죽는다.
    seen_in_payload: set[tuple] = set()

    # 건드리는 슬롯에 **이미 있는** 행들. replace_existing을 안 켜고 같은 파일을
    # 다시 올려도 행이 쌓이거나 제약 위반으로 죽지 않게 한다(예전엔 조용히 2배가
    # 됐고, 그게 이번 사고의 다른 얼굴이었다).
    existing_keys: set[tuple] = set()
    for plan_date, corner_id, meal_type in touched_slots:
        for menu_id, menu_role in db.query(WeeklyMenuPlan.menu_id, WeeklyMenuPlan.menu_role).filter(
            WeeklyMenuPlan.plan_date == plan_date,
            WeeklyMenuPlan.corner_id == corner_id,
            WeeklyMenuPlan.meal_type == meal_type,
        ):
            existing_keys.add((plan_date, corner_id, meal_type, menu_id, menu_role))

    for row in payload.rows:
        corner_id = corner_ids[row.corner_name]
        menu, is_new_menu = get_or_create_menu(db, row.menu_name)
        if is_new_menu:
            new_menus += 1

        slot_menu = (row.plan_date, corner_id, row.meal_type, menu.menu_id)
        if slot_menu in manual_keys:
            # 관리자 판단이 파서 결과를 이긴다. 다시 넣으면 중복이 된다.
            skipped_manual += 1
            continue
        full_key = (*slot_menu, row.menu_role)
        if full_key in seen_in_payload or full_key in existing_keys:
            skipped_duplicate += 1
            continue
        seen_in_payload.add(full_key)

        db.add(
            WeeklyMenuPlan(
                plan_date=row.plan_date,
                meal_type=row.meal_type,
                corner_id=corner_id,
                menu_id=menu.menu_id,
                menu_role=row.menu_role,
                is_new_menu=is_new_menu,
                source_row_raw=row.source_row_raw,
            )
        )
        inserted += 1

    db.commit()
    return IngestResult(
        received=len(payload.rows),
        inserted=inserted,
        new_menus=new_menus,
        new_corners=new_corners,
        skipped_manual=skipped_manual,
        skipped_duplicate=skipped_duplicate,
    )


@router.post("/meal-log", response_model=IngestResult)
def ingest_meal_log(payload: MealLogIngestRequest, db: Session = Depends(get_db)) -> IngestResult:
    inserted = 0
    new_menus = 0

    for row in payload.rows:
        employee = get_or_create_employee(db, row.employee_id, row.company_name)
        corner, _ = get_or_create_corner(db, row.corner_name)

        menu_id: int | None = None
        menu_snapshot_id: int | None = None

        if row.menu_name:
            # 식당취식정보(POS)에 실제 메뉴명("화면표시명(한글)")이 직접 실려 온다 —
            # 이걸로 바로 연결하는 게 아래 폴백보다 훨씬 신뢰도가 높다.
            menu, is_new_menu = get_or_create_menu(db, row.menu_name)
            menu_id = menu.menu_id
            if is_new_menu:
                new_menus += 1
        else:
            # 폴백: 메뉴명이 없는 소스(과거 mealdata.csv류)는 같은 날·같은 식사구분·
            # 같은 코너의 "메인" 메뉴를 그 날 실제 제공 메뉴로 간주해 연결한다.
            # 코너가 그 날 메인을 2개 이상 제공했다면(드묾) 모호하므로 연결하지 않는다.
            plan_date = row.eaten_at.date()
            main_plans = (
                db.query(WeeklyMenuPlan)
                .filter(
                    WeeklyMenuPlan.plan_date == plan_date,
                    WeeklyMenuPlan.meal_type == row.meal_type,
                    WeeklyMenuPlan.corner_id == corner.corner_id,
                    WeeklyMenuPlan.menu_role == MenuRole.MAIN,
                )
                .all()
            )
            menu_snapshot = main_plans[0] if len(main_plans) == 1 else None
            if menu_snapshot:
                menu_id = menu_snapshot.menu_id
                menu_snapshot_id = menu_snapshot.id

        db.add(
            MealLog(
                eaten_at=row.eaten_at,
                employee_id=employee.employee_id,
                meal_type=row.meal_type,
                corner_id=corner.corner_id,
                menu_id=menu_id,
                taste_score=row.taste_score,
                comment=row.comment,
                menu_snapshot_id=menu_snapshot_id,
            )
        )
        inserted += 1

    db.commit()
    return IngestResult(received=len(payload.rows), inserted=inserted, new_menus=new_menus)


@router.post("/weather-csv", response_model=WeatherIngestResult)
def ingest_weather_csv(payload: WeatherCsvIngestRequest, db: Session = Depends(get_db)) -> WeatherIngestResult:
    """PRD 7.1: 사내망이 data.go.kr에 못 닿는 배포를 위한 CSV 수동 임포트 경로(2026-08).

    scripts/import_weather_csv.py가 인터넷 되는 PC에서 만든 CSV를 이 형태로 올린다.
    stat_date가 PK라 재업로드 시 갱신(upsert)되고 중복이 쌓이지 않는다.
    """
    upserted = 0
    for row in payload.rows:
        had_rain = bool(row.precip_mm and row.precip_mm > 0)
        existing = db.get(DailyWeather, row.stat_date)
        if existing:
            existing.precip_mm = row.precip_mm
            existing.avg_temp_c = row.avg_temp_c
            existing.had_rain = had_rain
            existing.snow_cm = row.snow_cm
            existing.max_temp_c = row.max_temp_c
            existing.min_temp_c = row.min_temp_c
            existing.source = "csv_import"
        else:
            db.add(
                DailyWeather(
                    stat_date=row.stat_date,
                    precip_mm=row.precip_mm,
                    avg_temp_c=row.avg_temp_c,
                    had_rain=had_rain,
                    snow_cm=row.snow_cm,
                    max_temp_c=row.max_temp_c,
                    min_temp_c=row.min_temp_c,
                    source="csv_import",
                )
            )
        upserted += 1

    db.commit()
    return WeatherIngestResult(received=len(payload.rows), upserted=upserted)

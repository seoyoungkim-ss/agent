from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_ingest_token
from app.db import get_db
from app.models.enums import MenuRole, MenuRoleSource
from app.models.logs import MealLog, WeeklyMenuPlan
from app.schemas.ingest import (
    IngestResult,
    MealLogIngestRequest,
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

    if payload.replace_existing:
        # 슬롯 단위로 통째 교체한다. 이걸 안 하면 같은 파일을 다시 올릴 때
        # 행이 그대로 쌓여 편성 횟수·중복 판정이 전부 2배가 된다(dedup 없는 append).
        #
        # 단 role_source가 MANUAL인 행(관리자가 화면에서 직접 고친 주찬/부찬,
        # 건강가든 수기 입력)은 **교체 대상에서 제외**한다 — 사람이 손으로 넣은
        # 값이 재업로드로 조용히 날아가면 안 된다.
        slots = set()
        for row in payload.rows:
            corner, is_new_corner = get_or_create_corner(db, row.corner_name)
            if is_new_corner:
                new_corners += 1
            slots.add((row.plan_date, corner.corner_id, row.meal_type))
        for plan_date, corner_id, meal_type in slots:
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

    for row in payload.rows:
        corner, is_new_corner = get_or_create_corner(db, row.corner_name)
        if is_new_corner:
            new_corners += 1

        menu, is_new_menu = get_or_create_menu(db, row.menu_name)
        if is_new_menu:
            new_menus += 1

        db.add(
            WeeklyMenuPlan(
                plan_date=row.plan_date,
                meal_type=row.meal_type,
                corner_id=corner.corner_id,
                menu_id=menu.menu_id,
                menu_role=row.menu_role,
                is_new_menu=is_new_menu,
                source_row_raw=row.source_row_raw,
            )
        )
        inserted += 1

    db.commit()
    return IngestResult(
        received=len(payload.rows), inserted=inserted, new_menus=new_menus, new_corners=new_corners
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

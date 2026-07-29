import calendar
import datetime as dt
import io

import xlsxwriter
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.logs import MealLog
from app.models.master import CornerMaster, EmployeeMaster, MenuMaster
from app.models.stats import DailyDivisionStats, MenuPerformanceStats, MonthlyVoeCluster
from app.services.holidays import DayClassification, HolidayService
from app.services.llm_client import InternalLLMClient
from app.services.voe_category import OTHER_CATEGORY, VOE_CATEGORIES, classify_voe_categories
from app.services.voe_category_llm import classify_monthly_voe_via_llm

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _compute_weekly_summary(
    db: Session,
    start_date: dt.date | None,
    end_date: dt.date | None,
    classification: str | None,
) -> list[dict]:
    if start_date is None:
        today = dt.date.today()
        start_date = today - dt.timedelta(days=today.weekday())
    if end_date is None:
        end_date = start_date + dt.timedelta(days=6)

    holiday_svc = HolidayService(db)
    rows = (
        db.query(DailyDivisionStats)
        .filter(DailyDivisionStats.stat_date.between(start_date, end_date))
        .all()
    )
    daily_totals: dict[dt.date, int] = {}
    for row in rows:
        daily_totals[row.stat_date] = daily_totals.get(row.stat_date, 0) + row.headcount

    result = []
    current = start_date
    while current <= end_date:
        cls = holiday_svc.classify(current)
        if classification and cls.value != classification:
            current += dt.timedelta(days=1)
            continue
        result.append(
            {
                "date": current.isoformat(),
                "classification": cls.value,
                "headcount": daily_totals.get(current, 0),
            }
        )
        current += dt.timedelta(days=1)
    return result


@router.get("/weekly-summary")
def weekly_summary(
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    classification: str | None = Query(default=None, description="평일 | 주말+공휴일"),
    db: Session = Depends(get_db),
):
    """PRD 5.2: 실시간 주간 현황. 평일/주말+공휴일 필터를 공통으로 적용한다."""
    return _compute_weekly_summary(db, start_date, end_date, classification)


@router.get("/weekly-summary/export")
def weekly_summary_export(
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    classification: str | None = Query(default=None, description="평일 | 주말+공휴일"),
    db: Session = Depends(get_db),
):
    """PRD 5.2: 파트장/그룹장 보고용 엑셀 다운로드."""
    rows = _compute_weekly_summary(db, start_date, end_date, classification)

    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    sheet = workbook.add_worksheet("주간 현황")
    header_format = workbook.add_format({"bold": True, "bg_color": "#EEF2FF"})

    headers = ["날짜", "구분", "식수"]
    for col, header in enumerate(headers):
        sheet.write(0, col, header, header_format)
    for row_idx, row in enumerate(rows, start=1):
        sheet.write(row_idx, 0, row["date"])
        sheet.write(row_idx, 1, row["classification"])
        sheet.write(row_idx, 2, row["headcount"])
    sheet.set_column(0, 2, 16)
    workbook.close()

    filename = f"weekly-summary-{(start_date or dt.date.today()).isoformat()}.xlsx"
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/menu-history/{menu_name}")
def menu_history(menu_name: str, db: Session = Depends(get_db)):
    """PRD 5.2: 이번주 메뉴의 과거 제공 이력(만족도 추이)."""
    menu = db.query(MenuMaster).filter_by(menu_name=menu_name).one_or_none()
    if menu is None:
        raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다")

    stats = (
        db.query(MenuPerformanceStats)
        .filter_by(menu_id=menu.menu_id)
        .order_by(MenuPerformanceStats.period_start.desc())
        .all()
    )
    return [
        {
            "period_start": s.period_start.isoformat(),
            "period_end": s.period_end.isoformat(),
            "adjusted_score": s.adjusted_score,
            "evaluation_count": s.evaluation_count,
            "quadrant": s.quadrant_label.value if s.quadrant_label else None,
        }
        for s in stats
    ]


@router.get("/meal-log/export")
def meal_log_export(period_start: dt.date, period_end: dt.date, db: Session = Depends(get_db)):
    """전체 취식 데이터(원본 상세)를 기간 선택해 엑셀로 다운로드. 요약이 아닌 meal_log 개별 행 그대로 노출."""
    period_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())
    period_start_inclusive = dt.datetime.combine(period_start, dt.time())

    rows = (
        db.query(MealLog, EmployeeMaster, CornerMaster, MenuMaster)
        .join(EmployeeMaster, MealLog.employee_id == EmployeeMaster.employee_id)
        .join(CornerMaster, MealLog.corner_id == CornerMaster.corner_id)
        .outerjoin(MenuMaster, MealLog.menu_id == MenuMaster.menu_id)
        .filter(MealLog.eaten_at >= period_start_inclusive, MealLog.eaten_at < period_end_exclusive)
        .order_by(MealLog.eaten_at)
        .all()
    )

    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    sheet = workbook.add_worksheet("취식 데이터")
    header_format = workbook.add_format({"bold": True, "bg_color": "#EEF2FF"})
    datetime_format = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})

    headers = ["취식일시", "사번", "구분", "회사명", "식사구분", "코너", "메뉴", "맛평가", "의견"]
    for col, header in enumerate(headers):
        sheet.write(0, col, header, header_format)
    for row_idx, (meal, employee, corner, menu) in enumerate(rows, start=1):
        sheet.write_datetime(row_idx, 0, meal.eaten_at, datetime_format)
        sheet.write(row_idx, 1, employee.employee_id)
        sheet.write(row_idx, 2, employee.division.value)
        sheet.write(row_idx, 3, employee.company_name or "")
        sheet.write(row_idx, 4, meal.meal_type.value)
        sheet.write(row_idx, 5, corner.corner_name)
        sheet.write(row_idx, 6, menu.menu_name if menu else "")
        sheet.write(row_idx, 7, meal.taste_score.value if meal.taste_score else "")
        sheet.write(row_idx, 8, meal.comment or "")
    sheet.set_column(0, 0, 20)
    sheet.set_column(1, 7, 14)
    sheet.set_column(8, 8, 40)
    workbook.close()

    filename = f"meal-log-{period_start.isoformat()}_{period_end.isoformat()}.xlsx"
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/voe-clusters")
def voe_clusters(period: dt.date, db: Session = Depends(get_db)):
    """PRD 5.2: 월간 VOE 클러스터링 결과. period는 해당 월의 아무 날짜(YYYY-MM-01 권장)."""
    month_start = period.replace(day=1)
    rows = (
        db.query(MonthlyVoeCluster)
        .filter(MonthlyVoeCluster.period == month_start)
        .order_by(MonthlyVoeCluster.comment_count.desc())
        .all()
    )
    return [
        {
            "cluster_label": r.cluster_label,
            "representative_comment": r.representative_comment,
            "comment_count": r.comment_count,
            "keywords": r.keywords or [],
        }
        for r in rows
    ]


@router.get("/voe-by-category")
def voe_by_category(period: dt.date, db: Session = Depends(get_db)):
    """PRD 5.2/5.3: 월간 VOE를 맛/간/위생/서비스 고정 분류로 집계 — 리더 보고용.

    voe_clusters(K-means 자유형 클러스터)와 달리 카테고리가 매달 고정돼 있어
    한 달씩 비교하기 쉽다. period는 해당 월의 아무 날짜(YYYY-MM-01 권장).
    """
    month_start = period.replace(day=1)
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    month_end_exclusive = dt.datetime.combine(month_start.replace(day=last_day) + dt.timedelta(days=1), dt.time())
    month_start_dt = dt.datetime.combine(month_start, dt.time())

    rows = (
        db.query(MealLog.comment, MealLog.eaten_at, CornerMaster.corner_name, MealLog.voe_categories)
        .join(CornerMaster, MealLog.corner_id == CornerMaster.corner_id)
        .filter(
            MealLog.eaten_at >= month_start_dt,
            MealLog.eaten_at < month_end_exclusive,
            MealLog.comment.isnot(None),
        )
        .all()
    )

    buckets: dict[str, list[dict]] = {c: [] for c in [*VOE_CATEGORIES, OTHER_CATEGORY]}
    total_comments = 0
    for comment, eaten_at, corner_name, voe_categories in rows:
        if not comment or not comment.strip():
            continue
        total_comments += 1
        entry = {"eaten_at": eaten_at.isoformat(), "corner_name": corner_name, "comment": comment}
        # voe_categories가 채워져 있으면 그 달 LLM 배치 결과(voe_category_llm.py)를
        # 쓰고, 아직 배치가 안 돈 경우(NULL)만 규칙 기반으로 그때그때 대체한다.
        matched = voe_categories if voe_categories is not None else classify_voe_categories(comment)
        for category in matched or [OTHER_CATEGORY]:
            buckets[category].append(entry)

    return {
        "total_comments": total_comments,
        "categories": [
            {"category": category, "count": len(buckets[category]), "comments": buckets[category]}
            for category in [*VOE_CATEGORIES, OTHER_CATEGORY]
        ],
    }


@router.post("/voe-by-category/recompute")
async def recompute_voe_by_category(period: dt.date, db: Session = Depends(get_db)):
    """그 달의 meal_log.voe_categories를 사내 LLM으로 다시 계산한다(누적 저장).

    매달 새벽 스케줄러(app/scheduler.py::run_monthly_voe_category_classification)가
    지난달치를 자동으로 돌리지만, 이번 달 데이터를 배치를 기다리지 않고 바로
    반영하고 싶을 때 수동으로 트리거하는 용도다.
    """
    settings = get_settings()
    client = InternalLLMClient(settings)
    classified = await classify_monthly_voe_via_llm(db, period.replace(day=1), client)
    return {"classified_comments": classified}

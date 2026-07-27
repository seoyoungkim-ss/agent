import datetime as dt
import io

import xlsxwriter
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.master import MenuMaster
from app.models.stats import DailyDivisionStats, MenuPerformanceStats, MonthlyVoeCluster
from app.services.holidays import DayClassification, HolidayService

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

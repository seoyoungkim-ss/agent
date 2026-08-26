import calendar
import datetime as dt
import logging
import io
import statistics

import xlsxwriter
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.analysis import (
    _compute_plan_rule_check,
    _corner_id_by_menu_from_meal_log,
    _headcount_by_date_by_corner_bulk,
    corner_analysis,
    menu_performance,
)
from app.config import get_settings
from app.db import get_db
from app.models.enums import TASTE_SCORE_POINTS, MealType, MenuRole
from app.models.logs import MealLog, WeeklyMenuPlan
from app.models.master import CornerMaster, EmployeeMaster, MenuMaster
from app.models.stats import DailyDivisionStats, MenuPerformanceStats, MonthlyVoeCluster
from app.services.holidays import DayClassification, HolidayService
from app.services.improvement_points import (
    collect_planning_issues,
    select_priority_finding,
    summarize_priority_finding,
    summarize_voe_comments,
)
from app.services.llm_analysis import (
    KIND_MENU_TREND,
    KIND_VOE_BRIEFING,
    _collect_voe_briefing_facts,
    get_cached,
    save_analysis,
    summarize_voe_briefing,
)
from app.services.master_data import find_menu_by_name
from app.services.llm_client import InternalLLMClient
from app.services.menu_highlights import (
    compute_menu_satisfaction_trends,
    compute_new_menu_reactions,
    week_start,
)
from app.services.voe_category import OTHER_CATEGORY, VOE_CATEGORIES, classify_voe_categories
from app.services.voe_category_llm import classify_monthly_voe_via_llm
from app.services.voe_clustering import cluster_monthly_voe, cluster_voe_comments_for_period

logger = logging.getLogger(__name__)


def _trend_cause(db: Session, menu_id: int) -> dict:
    """캐시된 만족도 변화 원인. 없으면 빈 dict — 화면은 그냥 원인 줄을 안 그린다.

    §109: LLM이 "뚜렷한 원인을 특정하기 어렵다"고만 답한 경우도 근거가
    없다는 뜻은 마찬가지라 — 담당자 신고("이런 말은 안 하게, 모르면
    표기를 안 하는 걸로")에 따라 캐시가 있어도 빈 dict로 취급한다.
    """
    cached = get_cached(db, KIND_MENU_TREND, str(menu_id))
    if cached is None or "특정하기 어렵" in cached.summary:
        return {}
    return {
        "cause": cached.summary,
        "cause_keywords": cached.keywords or [],
        "cause_computed_at": cached.created_at.isoformat(),
    }


def _no_intake_main_menus(db: Session, period_start: dt.date, period_end: dt.date) -> list[dict]:
    """§86: 편성됐지만(MAIN) 그 기간 취식 기록이 0인 메뉴 — 예전엔
    menu_plan_performance의 action == "취식 기록 없음" 항목을 재사용했지만,
    그 엔드포인트가 편성 빈도×성과 재설계로 삭제돼 여기서 직접 계산한다.
    """
    plan_rows = (
        db.query(WeeklyMenuPlan.menu_id, MenuMaster.menu_name)
        .join(MenuMaster, WeeklyMenuPlan.menu_id == MenuMaster.menu_id)
        .filter(
            WeeklyMenuPlan.menu_role == MenuRole.MAIN,
            WeeklyMenuPlan.plan_date.between(period_start, period_end),
        )
        .all()
    )
    plan_name_by_id = {menu_id: menu_name for menu_id, menu_name in plan_rows}
    if not plan_name_by_id:
        return []

    log_start = dt.datetime.combine(period_start, dt.time())
    log_end = dt.datetime.combine(period_end, dt.time()) + dt.timedelta(days=1)
    logged_ids = {
        menu_id
        for (menu_id,) in db.query(MealLog.menu_id)
        .filter(MealLog.eaten_at >= log_start, MealLog.eaten_at < log_end, MealLog.menu_id.in_(plan_name_by_id))
        .distinct()
        .all()
    }
    no_intake_ids = set(plan_name_by_id) - logged_ids
    return [{"menu_name": plan_name_by_id[mid]} for mid in sorted(no_intake_ids, key=lambda mid: plan_name_by_id[mid])]


def _collect_planning_facts(db: Session, period_start: dt.date, period_end: dt.date) -> list[str]:
    """편성 축 사실 수집 — 이미 만들어 둔 순수 함수들을 조합만 한다(§36.1 관례).

    지연 임포트: analysis.py가 dashboard.py를 참조하지 않도록 호출 시점에 가져온다.
    """
    from app.api.analysis import weekly_menu_combination_check, weekly_menu_rotation

    rotation = weekly_menu_rotation(period_start=period_start, period_end=period_end, db=db)
    clash = weekly_menu_combination_check(period_start=period_start, period_end=period_end, db=db)

    clash_slots = [
        s
        for s in clash["slots"]
        if s["ingredient_clashes"] or s["vector_clashes"]
    ]
    no_intake = _no_intake_main_menus(db, period_start, period_end)
    return collect_planning_issues(
        overused=rotation["overused"],
        no_intake_menus=no_intake,
        clash_slot_count=len(clash_slots),
    )


router = APIRouter(prefix="/dashboard", tags=["dashboard"])

MENU_HIGHLIGHTS_WINDOW_DAYS = 180  # 6.3절 menu_performance_stats 롤링 윈도우와 동일 범위
NEW_MENU_WINDOW_DAYS = 30  # "최근 도입된 신메뉴"로 볼 기간


def _compute_weekly_summary(
    db: Session,
    start_date: dt.date | None,
    end_date: dt.date | None,
    classification: str | None,
    meal_types: list[MealType] | None = None,
) -> list[dict]:
    if start_date is None:
        today = dt.date.today()
        start_date = today - dt.timedelta(days=today.weekday())
    if end_date is None:
        end_date = start_date + dt.timedelta(days=6)

    holiday_svc = HolidayService(db)
    query = db.query(DailyDivisionStats).filter(DailyDivisionStats.stat_date.between(start_date, end_date))
    if meal_types:
        query = query.filter(DailyDivisionStats.meal_type.in_(meal_types))
    rows = query.all()
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
    meal_types: list[MealType] | None = Query(
        default=None, description="조식/중식/석식 중 선택 — 여러 개면 합산, 생략 시 전체 합산"
    ),
    db: Session = Depends(get_db),
):
    """PRD 5.2: 실시간 주간 현황. 평일/주말+공휴일 필터를 공통으로 적용한다."""
    return _compute_weekly_summary(db, start_date, end_date, classification, meal_types)


@router.get("/weekly-summary/export")
def weekly_summary_export(
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    classification: str | None = Query(default=None, description="평일 | 주말+공휴일"),
    meal_types: list[MealType] | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """PRD 5.2: 파트장/그룹장 보고용 엑셀 다운로드."""
    rows = _compute_weekly_summary(db, start_date, end_date, classification, meal_types)

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
    menu = find_menu_by_name(db, menu_name)
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


@router.get("/menu-appearance-history/{menu_name}")
def menu_appearance_history(menu_name: str, db: Session = Depends(get_db)):
    """§104: 실제 등장일별 만족도 + 누적 평균 — "금주 메뉴 VOE 상세" 아코디언용.

    menu_history()가 쓰는 MenuPerformanceStats는 나이트 배치가 만든 기간
    스냅샷이라 "이 메뉴가 실제로 나온 날짜"를 보여주지 못한다(§104 배치 중복
    버그) — meal_log를 date(eaten_at) 단위로 직접 묶어 등장일을 만든다.
    """
    menu = find_menu_by_name(db, menu_name)
    if menu is None:
        raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다")

    rows = (
        db.query(MealLog)
        .filter(MealLog.menu_id == menu.menu_id)
        .order_by(MealLog.eaten_at.asc())
        .all()
    )
    by_date: dict[dt.date, list[MealLog]] = {}
    for r in rows:
        by_date.setdefault(r.eaten_at.date(), []).append(r)

    cumulative_scores: list[float] = []
    result = []
    for date in sorted(by_date):
        day_scores = [TASTE_SCORE_POINTS[r.taste_score] for r in by_date[date] if r.taste_score is not None]
        day_avg = statistics.fmean(day_scores) if day_scores else None
        cumulative_scores.extend(day_scores)
        cumulative_avg = statistics.fmean(cumulative_scores) if cumulative_scores else None
        result.append(
            {
                "date": date.isoformat(),
                "avg_score": round(day_avg, 2) if day_avg is not None else None,
                "cumulative_avg_score": round(cumulative_avg, 2) if cumulative_avg is not None else None,
            }
        )
    return list(reversed(result))  # 최신 등장일이 위로


@router.get("/menu-comments/{menu_name}")
def menu_comments(menu_name: str, limit: int = 20, db: Session = Depends(get_db)):
    """PRD 5.2: 이번주 메뉴의 과거 VOE 원문 코멘트 — "금주 메뉴 VOE 상세" 화면용.

    menu_history(점수 이력)와 짝을 이룬다 — 점수만으로는 "무슨 내용인지" 알 수
    없다는 피드백(2026-07, improvement_points의 voe_summary와 같은 문제의식)에
    따라 원문을 그대로 보여준다.
    """
    menu = find_menu_by_name(db, menu_name)
    if menu is None:
        raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다")

    rows = (
        db.query(MealLog)
        .filter(MealLog.menu_id == menu.menu_id, MealLog.comment.isnot(None))
        .order_by(MealLog.eaten_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "eaten_at": r.eaten_at.isoformat(),
            "taste_score": r.taste_score.value if r.taste_score else None,
            "comment": r.comment,
        }
        for r in rows
        if r.comment and r.comment.strip()
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


def _corner_stats_from_meal_log(
    db: Session, period_start: dt.date, period_end: dt.date, meal_type: MealType | None = None
) -> list[dict]:
    """§119: 코너별 통계를 취식기록(meal_log)에서 직접 집계한다 — 배치 집계
    (daily_corner_stats) 기반인 corner_analysis와 달리 배치가 그 기간에
    아직 안 돌았어도 항상 최신값을 보여준다(§117의 데이터 소스 원칙과 동일).
    Take Out/미캠회관(전골) 제외는 적용하지 않는다 — corner_analysis
    기본값·§117 corner_heavy_rain_ranking과 같은 관례(코너 단위 집계는
    제외하지 않음).
    """
    headcount_by_corner = _headcount_by_date_by_corner_bulk(db, period_start, period_end, meal_type)

    period_start_dt = dt.datetime.combine(period_start, dt.time())
    period_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())
    taste_query = db.query(MealLog.corner_id, MealLog.taste_score).filter(
        MealLog.corner_id.isnot(None),
        MealLog.eaten_at >= period_start_dt,
        MealLog.eaten_at < period_end_exclusive,
        MealLog.taste_score.isnot(None),
    )
    if meal_type is not None:
        taste_query = taste_query.filter(MealLog.meal_type == meal_type)
    scores_by_corner: dict[int, list[int]] = {}
    for corner_id, taste_score in taste_query.all():
        scores_by_corner.setdefault(corner_id, []).append(TASTE_SCORE_POINTS[taste_score])

    corners = {c.corner_id: c.corner_name for c in db.query(CornerMaster).all()}

    rows = []
    for corner_id, headcount_by_date in headcount_by_corner.items():
        counts = list(headcount_by_date.values())
        scores = scores_by_corner.get(corner_id, [])
        rows.append(
            {
                "corner_id": corner_id,
                "corner_name": corners.get(corner_id),
                "avg_headcount": round(statistics.fmean(counts), 1),
                "total_headcount": sum(counts),
                "day_count": len(counts),
                "avg_taste_score": round(statistics.fmean(scores), 2) if scores else None,
            }
        )
    rows.sort(key=lambda r: -r["avg_headcount"])
    return rows


@router.get("/weekly-menu/negotiation-export")
async def weekly_menu_negotiation_export(
    period_start: dt.date,
    period_end: dt.date,
    db: Session = Depends(get_db),
):
    """§118~§119: 식당협의용 엑셀 — 그 주(period_start~period_end) 편성
    규칙 위반 내용 + 코너별 통계(취식기록 직접 집계) + 오늘 기준 최근 2주
    VOE 클러스터링 내용을 시트 3개로 묶는다.
    """
    rule_check = _compute_plan_rule_check(db, period_start, period_end)
    corner_stats = _corner_stats_from_meal_log(db, period_start, period_end, meal_type=MealType.LUNCH)

    voe_period_end = dt.date.today()
    voe_period_start = voe_period_end - dt.timedelta(days=13)  # 최근 2주(14일, 오늘 포함)
    settings = get_settings()
    llm_client = InternalLLMClient(settings)
    try:
        voe_clusters = await cluster_voe_comments_for_period(db, voe_period_start, voe_period_end, llm_client)
    except Exception as exc:
        # 다른 VOE LLM 엔드포인트(recompute_voe_clusters 등)와 같은 관례 —
        # 원인 불명 500 대신 detail에 실제 예외를 남긴다.
        raise HTTPException(
            status_code=502,
            detail=f"VOE 클러스터링 실패(사내 LLM 채팅 응답 오류 가능성): {exc}",
        ) from exc

    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    header_format = workbook.add_format({"bold": True, "bg_color": "#EEF2FF"})

    sheet1 = workbook.add_worksheet("규칙 위반")
    headers1 = ["구분", "날짜", "내용"]
    for col, h in enumerate(headers1):
        sheet1.write(0, col, h, header_format)
    row = 1
    rule_labels = {"hangover": "해장 메뉴 미달", "noodle": "면류 과다", "spicy_red_broth": "매운 국물 과다"}
    for key, label in rule_labels.items():
        for day in rule_check[key]:
            if day["ok"]:
                continue
            detail = (
                f"{day['count']}건"
                + (f"(기준 {day['limit']}건 초과)" if day["limit"] else "(최소 1건 필요, 0건)")
                + " — "
                + ", ".join(f"{m['menu_name']}({m['corner_name']})" for m in day["matches"])
            )
            sheet1.write(row, 0, label)
            sheet1.write(row, 1, day["plan_date"])
            sheet1.write(row, 2, detail)
            row += 1
    for v in rule_check["low_headcount_reuse"]["violations"]:
        sheet1.write(row, 0, "저조 식수 재편성")
        sheet1.write(row, 1, v["matches"][0]["plan_date"] if v["matches"] else "")
        sheet1.write(
            row,
            2,
            f"{v['menu_name']}({v['corner_name']}) — 지난 등장 {v['last_appearance_date']}에 "
            f"{v['last_appearance_headcount']}식(기준 200식 이하)",
        )
        row += 1
    if row == 1:
        sheet1.write(row, 0, "위반 없음")
    sheet1.set_column(0, 0, 16)
    sheet1.set_column(1, 1, 12)
    sheet1.set_column(2, 2, 70)

    sheet2 = workbook.add_worksheet("코너별 통계")
    headers2 = ["코너명", "평균 식수", "총 식수", "표본(일)", "평균 만족도"]
    for col, h in enumerate(headers2):
        sheet2.write(0, col, h, header_format)
    for i, c in enumerate(corner_stats, start=1):
        sheet2.write(i, 0, c["corner_name"])
        sheet2.write(i, 1, c["avg_headcount"])
        sheet2.write(i, 2, c["total_headcount"])
        sheet2.write(i, 3, c["day_count"])
        sheet2.write(i, 4, c["avg_taste_score"] if c["avg_taste_score"] is not None else "")
    if not corner_stats:
        sheet2.write(1, 0, "이 기간에 취식 기록이 없습니다")
    sheet2.set_column(0, 0, 20)
    sheet2.set_column(1, 4, 12)

    sheet3 = workbook.add_worksheet("VOE 클러스터링(최근 2주)")
    headers3 = ["주제", "건수", "키워드", "대표 코멘트"]
    for col, h in enumerate(headers3):
        sheet3.write(0, col, h, header_format)
    for i, (label, representative, count, keywords) in enumerate(voe_clusters, start=1):
        sheet3.write(i, 0, label)
        sheet3.write(i, 1, count)
        sheet3.write(i, 2, ", ".join(keywords))
        sheet3.write(i, 3, representative)
    if not voe_clusters:
        sheet3.write(1, 0, "이 기간에 등록된 의견이 없습니다")
    sheet3.set_column(0, 0, 16)
    sheet3.set_column(1, 1, 8)
    sheet3.set_column(2, 2, 30)
    sheet3.set_column(3, 3, 60)

    workbook.close()
    buffer.seek(0)
    filename = f"cafeteria-negotiation-{period_start.isoformat()}_{period_end.isoformat()}.xlsx"
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


def _compute_voe_by_category(db: Session, period: dt.date) -> dict:
    month_start = period.replace(day=1)
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    month_end_exclusive = dt.datetime.combine(month_start.replace(day=last_day) + dt.timedelta(days=1), dt.time())
    month_start_dt = dt.datetime.combine(month_start, dt.time())

    rows = (
        db.query(
            MealLog.comment, MealLog.eaten_at, CornerMaster.corner_name, MenuMaster.menu_name, MealLog.voe_categories
        )
        .join(CornerMaster, MealLog.corner_id == CornerMaster.corner_id)
        .outerjoin(MenuMaster, MealLog.menu_id == MenuMaster.menu_id)  # menu_id는 nullable(2026-08)
        .filter(
            MealLog.eaten_at >= month_start_dt,
            MealLog.eaten_at < month_end_exclusive,
            MealLog.comment.isnot(None),
        )
        .all()
    )

    buckets: dict[str, list[dict]] = {c: [] for c in [*VOE_CATEGORIES, OTHER_CATEGORY]}
    total_comments = 0
    for comment, eaten_at, corner_name, menu_name, voe_categories in rows:
        if not comment or not comment.strip():
            continue
        total_comments += 1
        entry = {
            "eaten_at": eaten_at.isoformat(),
            "corner_name": corner_name,
            "menu_name": menu_name,
            "comment": comment,
        }
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


@router.get("/voe-by-category")
def voe_by_category(period: dt.date, db: Session = Depends(get_db)):
    """PRD 5.2/5.3: 월간 VOE를 맛/간/위생/서비스 고정 분류로 집계 — 리더 보고용.

    voe_clusters(K-means 자유형 클러스터)와 달리 카테고리가 매달 고정돼 있어
    한 달씩 비교하기 쉽다. period는 해당 월의 아무 날짜(YYYY-MM-01 권장).
    """
    return _compute_voe_by_category(db, period)


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


@router.post("/voe-clusters/recompute")
async def recompute_voe_clusters(period: dt.date, db: Session = Depends(get_db)):
    """그 달의 VOE 코멘트를 사내 LLM 채팅 그룹핑으로 다시 클러스터링한다.

    매달 새벽 스케줄러(app/scheduler.py)가 지난달치를 자동으로 돌리지만,
    voe-by-category/recompute와 마찬가지로 이번 달 데이터를 화면에서 바로
    재계산하고 싶을 때 쓰는 수동 트리거 — 지금까지는 이 엔드포인트가 없어
    스케줄러 전용이었다(2026-07, "주관식 VOE" 서브탭 신설과 함께 추가).
    """
    settings = get_settings()
    client = InternalLLMClient(settings)
    try:
        clusters_created = await cluster_monthly_voe(db, period.replace(day=1), client)
    except Exception as exc:
        # 이 경로는 사내 LLM 채팅 게이트웨이 호출을 포함해 외부 의존성이
        # 많다 — 원인 불명 500 대신 어떤 예외였는지 detail에 남겨 디버깅
        # 가능하게 한다(2026-07, 500 에러 신고 조사 중 추가).
        raise HTTPException(
            status_code=502,
            detail=f"VOE 클러스터링 실패(사내 LLM 채팅 응답 오류 가능성): {exc}",
        ) from exc
    return {"clusters_created": clusters_created}


@router.get("/voe-briefing")
def voe_briefing(period: dt.date, db: Session = Depends(get_db)):
    """§80: 이달의 VOE AI 브리핑 — voe_clusters(월간 클러스터링)를 재사용해
    여러 테마를 한 번에 요약한 캐시 조회 전용 엔드포인트.

    클러스터링(POST /voe-clusters/recompute)이 그 달에 아직 한 번도
    안 돌았으면 has_clusters=false로 알려준다 — 화면이 "먼저 클러스터링을
    계산하세요" 안내로 구분할 수 있게.
    """
    month_start = period.replace(day=1)
    has_clusters = (
        db.query(MonthlyVoeCluster.id).filter(MonthlyVoeCluster.period == month_start).first() is not None
    )
    cached = get_cached(db, KIND_VOE_BRIEFING, month_start.isoformat())
    return {
        "has_clusters": has_clusters,
        "briefing": cached.summary if cached else None,
        "briefing_computed_at": cached.created_at.isoformat() if cached else None,
    }


@router.post("/voe-briefing/recompute")
async def recompute_voe_briefing(period: dt.date, db: Session = Depends(get_db)):
    """그 달의 VOE 클러스터를 사내 LLM으로 다중 테마 브리핑 문장으로 요약한다.

    voe-clusters/recompute와 마찬가지로 수동 트리거 — 재임베딩/재군집은
    하지 않고 이미 저장된 MonthlyVoeCluster 행만 재사용한다.
    """
    month_start = period.replace(day=1)
    facts = _collect_voe_briefing_facts(db, month_start)
    settings = get_settings()
    llm_client = InternalLLMClient(settings)
    summary = await summarize_voe_briefing(llm_client, facts)
    save_analysis(
        db,
        kind=KIND_VOE_BRIEFING,
        subject_key=month_start.isoformat(),
        period_start=month_start,
        period_end=month_start,
        summary=summary,
        facts=facts,
    )
    return {"briefing": summary, "has_clusters": bool(facts["clusters"])}


@router.get("/menu-highlights")
def menu_highlights(db: Session = Depends(get_db)):
    """PRD 5.3: 메뉴 만족도 급상승/급하락 + 신메뉴 초기 반응 — 홈 화면용.

    메뉴는 매주 나오지 않으므로 "이번 주 vs 지난 주" 대신 메뉴별 "마지막 등장
    주 vs 그 직전 등장 주"를 비교한다(app/services/menu_highlights.py). 저장
    없이 요청 시점에 바로 집계한다 — menu_performance_stats(6.3절, 180일
    롤링 단일 구간)와는 목적이 달라 서로 건드리지 않는다.
    """
    settings = get_settings()
    today = dt.date.today()
    window_start_dt = dt.datetime.combine(today - dt.timedelta(days=MENU_HIGHLIGHTS_WINDOW_DAYS), dt.time())
    window_end_dt = dt.datetime.combine(today + dt.timedelta(days=1), dt.time())

    rows = (
        db.query(
            MealLog.menu_id, MealLog.eaten_at, MealLog.taste_score, MenuMaster.menu_name, CornerMaster.corner_name
        )
        .join(MenuMaster, MealLog.menu_id == MenuMaster.menu_id)
        .join(CornerMaster, MealLog.corner_id == CornerMaster.corner_id)
        .filter(
            MealLog.eaten_at >= window_start_dt,
            MealLog.eaten_at < window_end_dt,
            MealLog.menu_id.isnot(None),
            MealLog.taste_score.isnot(None),
        )
        .all()
    )

    global_avg_score = statistics.fmean([TASTE_SCORE_POINTS[r.taste_score] for r in rows]) if rows else 3.0

    menu_names: dict[int, str] = {}
    menu_corners: dict[int, str | None] = {}
    weekly_scores: dict[int, dict[dt.date, list]] = {}
    scores_by_menu: dict[int, list] = {}
    for menu_id, eaten_at, taste_score, menu_name, corner_name in rows:
        menu_names[menu_id] = menu_name
        menu_corners[menu_id] = corner_name
        weekly_scores.setdefault(menu_id, {}).setdefault(week_start(eaten_at.date()), []).append(taste_score)
        scores_by_menu.setdefault(menu_id, []).append(taste_score)

    rising, falling = compute_menu_satisfaction_trends(
        weekly_scores,
        menu_names,
        menu_corners,
        global_avg_score=global_avg_score,
        shrinkage_m=settings.menu_score_shrinkage_m,
        low_sample_threshold=settings.menu_score_low_sample_threshold,
    )

    # 신메뉴 하이라이트는 메인메뉴만 의미가 있다(부찬은 "신메뉴"로 취급 안 함).
    new_menu_window_start = today - dt.timedelta(days=NEW_MENU_WINDOW_DAYS)
    new_menu_rows = (
        db.query(WeeklyMenuPlan.menu_id, MenuMaster.menu_name, CornerMaster.corner_name, WeeklyMenuPlan.plan_date)
        .join(MenuMaster, WeeklyMenuPlan.menu_id == MenuMaster.menu_id)
        .join(CornerMaster, WeeklyMenuPlan.corner_id == CornerMaster.corner_id)
        .filter(
            WeeklyMenuPlan.is_new_menu.is_(True),
            WeeklyMenuPlan.plan_date >= new_menu_window_start,
            WeeklyMenuPlan.menu_role == MenuRole.MAIN,
        )
        .all()
    )
    new_menus: dict[int, tuple[str, str | None, dt.date]] = {}
    for menu_id, menu_name, corner_name, plan_date in new_menu_rows:
        existing = new_menus.get(menu_id)
        first_plan_date = min(plan_date, existing[2]) if existing else plan_date
        new_menus[menu_id] = (menu_name, corner_name, first_plan_date)

    # 관리자 수동 지정(2026-07) — 자동판정(위 30일 창) 위에 얹는다. override=True는
    # 30일 창과 무관하게 계속 노출(해제 전까지), override=False는 자동판정으로
    # 떴어도 강제로 뺀다. 코너명은 weekly_menu_plan이 아니라 meal_log 최빈
    # 코너로 찾는다(analysis.py의 관례와 동일 — weekly_menu_plan은 누락되기 쉬움).
    manual_new_menu_ids: set[int] = set()
    override_rows = db.query(MenuMaster).filter(MenuMaster.new_menu_override.isnot(None)).all()
    if override_rows:
        corner_id_by_menu = _corner_id_by_menu_from_meal_log(db)
        corner_name_by_id = {c.corner_id: c.corner_name for c in db.query(CornerMaster).all()}
        # 식단표(weekly_menu_plan)에 부찬으로만 등장한 메뉴는 관리자가 수동
        # 지정해도 하이라이트에서 뺀다. 식단표에 아예 등장한 적 없는 메뉴
        # (취식기록으로만 존재)는 역할을 판단할 근거가 없으니 그대로 둔다.
        plan_role_rows = db.query(WeeklyMenuPlan.menu_id, WeeklyMenuPlan.menu_role).distinct().all()
        main_menu_ids = {menu_id for menu_id, role in plan_role_rows if role == MenuRole.MAIN}
        side_only_menu_ids = {menu_id for menu_id, _role in plan_role_rows} - main_menu_ids
        for menu in override_rows:
            if menu.new_menu_override is False:
                new_menus.pop(menu.menu_id, None)
                continue
            if menu.menu_id in side_only_menu_ids:
                continue  # 부찬으로만 쓰인 메뉴는 수동 지정해도 하이라이트에 안 뜬다
            marked_on = menu.new_menu_marked_on or today
            corner_id = corner_id_by_menu.get(menu.menu_id)
            corner_name = corner_name_by_id.get(corner_id) if corner_id is not None else None
            new_menus[menu.menu_id] = (menu.menu_name, corner_name, marked_on)
            manual_new_menu_ids.add(menu.menu_id)

    new_menu_reactions = compute_new_menu_reactions(
        new_menus,
        scores_by_menu,
        global_avg_score=global_avg_score,
        shrinkage_m=settings.menu_score_shrinkage_m,
        low_sample_threshold=settings.menu_score_low_sample_threshold,
        today=today,
    )

    def _trend(e):
        return {
            "menu_id": e.menu_id,
            "menu_name": e.menu_name,
            "corner_name": e.corner_name,
            "recent_score": e.recent_score,
            "prior_score": e.prior_score,
            "delta": e.delta,
            "evaluation_count": e.evaluation_count,
            "date": e.recent_week.isoformat(),
            # ⚠️ 아래 둘은 **날짜가 아니라 ISO 주의 월요일**이다(§28: 메뉴가 매주
            # 나오지 않으므로 달력 주가 아니라 "그 메뉴가 나온 주"끼리 비교한다).
            # 화면 문구도 "7/13 주"처럼 주 단위임이 드러나게 써야 오해가 없다.
            "recent_week": e.recent_week.isoformat(),
            "prior_week": e.prior_week.isoformat(),
            "prior_evaluation_count": e.prior_evaluation_count,
            # 만족도가 왜 변했는지 — 새벽 배치가 미리 계산해 둔 것을 읽기만 한다.
            # 여기서 LLM을 부르면 홈 로드가 다시 느려진다(§50). 최대 6건이고
            # (kind, subject_key) 인덱스 조회라 비용이 사실상 없다.
            **_trend_cause(db, e.menu_id),
        }

    def _new_menu(e):
        return {
            "menu_id": e.menu_id,
            "menu_name": e.menu_name,
            "corner_name": e.corner_name,
            "adjusted_score": e.adjusted_score,
            "evaluation_count": e.evaluation_count,
            "days_since_introduction": e.days_since_introduction,
            "needs_attention": e.days_since_introduction >= 7 and e.evaluation_count == 0,
            "is_manual": e.menu_id in manual_new_menu_ids,
        }

    return {
        "rising": [_trend(e) for e in rising],
        "falling": [_trend(e) for e in falling],
        "new_menus": [_new_menu(e) for e in new_menu_reactions],
    }


@router.get("/improvement-points")
async def improvement_points(period_start: dt.date, period_end: dt.date, db: Session = Depends(get_db)):
    """홈 현황 "개선 필요 포인트" (2026-08 담당자 프롬프트로 전면 교체).

    예전엔 혼잡도/만족도/VOE/편성·운영 네 축에서 각각 최대 몇 건씩 뽑아
    리스트로 보여줬다. 이제는 담당자가 지정한 우선순위(만족도 → VOE →
    편성·운영 → 혼잡도)로 검토해 **가장 급한 이슈 하나만** 보여준다 — 어느
    축에서도 유의미한 이슈가 없으면 "특이사항 없음"(status: "no_issue").
    우선순위 판정은 `improvement_points.select_priority_finding`(순수 함수),
    문구 다듬기는 `summarize_priority_finding`(LLM + 폴백)이 담당한다.

    전부 이미 계산된 값을 재사용한다: 코너 통계(`analysis.py::corner_analysis`),
    메뉴 4분면(`analysis.py::menu_performance` — 사전에 recompute가 돼 있어야
    함), 이번 달/지난 달 VOE 카테고리 집계(`_compute_voe_by_category`), 편성
    사실(`_collect_planning_facts`).

    선정된 이슈가 VOE 축이면, 해당 카테고리의 원문 코멘트 일부를 사내 LLM에
    보내 만든 1~2문장 요약(voe_summary)을 덧붙인다 — 건수만으로는 "무슨
    내용인지"를 알 수 없다는 피드백(2026-07)에 따른 것.
    """
    corners = corner_analysis(period_start=period_start, period_end=period_end, db=db)
    menu_rows = menu_performance(period_start=period_start, period_end=period_end, db=db)

    current_month = period_end.replace(day=1)
    prior_month_end = current_month - dt.timedelta(days=1)
    prior_month = prior_month_end.replace(day=1)
    current_voe = _compute_voe_by_category(db, current_month)
    prior_voe = _compute_voe_by_category(db, prior_month) if prior_month != current_month else None

    planning_issues: list[str] = []
    try:
        planning_issues = _collect_planning_facts(db, period_start, period_end)
    except Exception:
        # 편성 축 사실 수집이 실패해도 나머지 축은 판단할 수 있어야 한다(§44 결론).
        logger.exception("편성 축 사실 수집 실패 — 편성 축 없이 판단한다")

    finding = select_priority_finding(
        corners=corners,
        menu_rows=menu_rows,
        current_voe=current_voe,
        prior_voe=prior_voe,
        planning_issues=planning_issues,
    )
    if finding is None:
        return {"status": "no_issue"}

    settings = get_settings()
    llm_client = InternalLLMClient(settings)
    result = await summarize_priority_finding(llm_client, finding)
    response = {"status": "issue", "axis": finding.axis, **result}

    if finding.axis == "voe" and finding.voe_category:
        comments_by_category = {
            c["category"]: [entry["comment"] for entry in c["comments"]] for c in current_voe.get("categories", [])
        }
        voe_summary = await summarize_voe_comments(
            llm_client, finding.voe_category, comments_by_category.get(finding.voe_category, [])
        )
        if voe_summary:
            response["voe_summary"] = voe_summary
    return response

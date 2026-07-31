import calendar
import datetime as dt
import io
import statistics

import xlsxwriter
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.analysis import _corner_id_by_menu_from_meal_log, corner_analysis, menu_performance
from app.config import get_settings
from app.db import get_db
from app.models.enums import TASTE_SCORE_POINTS, MealType, MenuRole
from app.models.logs import MealLog, WeeklyMenuPlan
from app.models.master import CornerMaster, EmployeeMaster, MenuMaster
from app.models.stats import DailyDivisionStats, MenuPerformanceStats, MonthlyVoeCluster
from app.services.holidays import DayClassification, HolidayService
from app.services.improvement_points import (
    select_congestion_points,
    select_satisfaction_points,
    select_voe_points,
    summarize_voe_comments,
)
from app.services.llm_client import InternalLLMClient
from app.services.menu_highlights import (
    compute_menu_satisfaction_trends,
    compute_new_menu_reactions,
    week_start,
)
from app.services.voe_category import OTHER_CATEGORY, VOE_CATEGORIES, classify_voe_categories
from app.services.voe_category_llm import classify_monthly_voe_via_llm
from app.services.voe_clustering import cluster_monthly_voe

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


@router.get("/menu-comments/{menu_name}")
def menu_comments(menu_name: str, limit: int = 20, db: Session = Depends(get_db)):
    """PRD 5.2: 이번주 메뉴의 과거 VOE 원문 코멘트 — "금주 메뉴 VOE 상세" 화면용.

    menu_history(점수 이력)와 짝을 이룬다 — 점수만으로는 "무슨 내용인지" 알 수
    없다는 피드백(2026-07, improvement_points의 voe_summary와 같은 문제의식)에
    따라 원문을 그대로 보여준다.
    """
    menu = db.query(MenuMaster).filter_by(menu_name=menu_name).one_or_none()
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
    """그 달의 VOE 코멘트를 사내 LLM 임베딩+KMeans로 다시 클러스터링한다.

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
        # 이 경로는 사내 LLM 임베딩 게이트웨이 호출을 포함해 외부 의존성이
        # 많다 — 원인 불명 500 대신 어떤 예외였는지 detail에 남겨 디버깅
        # 가능하게 한다(2026-07, 500 에러 신고 조사 중 추가).
        raise HTTPException(
            status_code=502,
            detail=f"VOE 클러스터링 실패(사내 LLM 임베딩/응답 오류 가능성): {exc}",
        ) from exc
    return {"clusters_created": clusters_created}


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
    """홈 현황 "개선 포인트" — 혼잡도/만족도/VOE 세 축에서 지금 손볼 만한 지점.

    전부 이미 계산된 값을 재사용한다: 코너 통계(`analysis.py::corner_analysis`),
    메뉴 4분면(`analysis.py::menu_performance` — 사전에 recompute가 돼 있어야
    함), 이번 달/지난 달 VOE 카테고리 집계(`_compute_voe_by_category`).

    VOE 포인트에는 해당 카테고리의 원문 코멘트 일부를 사내 LLM에 보내 만든
    1~2문장 요약(voe_summary)을 덧붙인다 — 건수만으로는 "무슨 내용인지"를
    알 수 없다는 피드백(2026-07)에 따른 것.
    """
    corners = corner_analysis(period_start=period_start, period_end=period_end, db=db)
    menu_rows = menu_performance(period_start=period_start, period_end=period_end, db=db)

    current_month = period_end.replace(day=1)
    prior_month_end = current_month - dt.timedelta(days=1)
    prior_month = prior_month_end.replace(day=1)
    current_voe = _compute_voe_by_category(db, current_month)
    prior_voe = _compute_voe_by_category(db, prior_month) if prior_month != current_month else None

    points = [
        *select_congestion_points(corners),
        *select_satisfaction_points(menu_rows),
        *select_voe_points(current_voe, prior_voe),
    ]

    comments_by_category = {
        c["category"]: [entry["comment"] for entry in c["comments"]] for c in current_voe.get("categories", [])
    }
    settings = get_settings()
    llm_client = InternalLLMClient(settings)

    results = []
    for p in points:
        entry = {"axis": p.axis, "title": p.title, "detail": p.detail, "severity": p.severity}
        if p.axis == "voe" and p.voe_category:
            entry["voe_summary"] = await summarize_voe_comments(
                llm_client, p.voe_category, comments_by_category.get(p.voe_category, [])
            )
        results.append(entry)
    return results

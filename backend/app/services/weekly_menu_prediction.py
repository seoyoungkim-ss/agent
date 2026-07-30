"""주간 식단표 슬롯(메인메뉴)의 예상 영향.

숫자 계산(`compute_predicted_numbers`)과 LLM 코멘트(`compute_predicted_impact`)를
분리했다 — 격자표 전체(코너×요일)를 한 번에 비교하려면 슬롯 수만큼 반복
계산해야 하는데, 슬롯마다 LLM을 호출하면 느려진다(2026-07 사용자 확인).
숫자만 필요한 "전체 예측 비교"는 `compute_predicted_numbers_for_period`로
빠르게 일괄 계산하고, LLM 코멘트가 들어간 상세 패널은 슬롯 하나를 클릭했을
때만 `compute_predicted_impact`를 호출한다.

기존 만족도/식수(menu_performance_stats), 이 조합(메인+부찬)의 과거 성적
(menu_combination.py), 예상 점유율/식수(코너 baseline × 메뉴 인기도 배수 ×
분당 처리량 비율을 기하평균으로 합성)는 숫자로 계산한다. "코어층 영향"과
"코너간 메뉴 경쟁"은 이 코드베이스에 확정된 계산 공식이 없어(코어층 분류는
직원 집합 분류만 있고, 교차-코너 경쟁 모델은 아예 없음, 2026-07 확인) 실제
신호(코어층 방문 빈도, 같은 날 경쟁 코너의 인기메뉴 여부)를 LLM에게 근거로
주고 2~3문장 정성 코멘트로만 받는다(사용자도 이 방식에 동의함) — 실제 수치를
지어내지 않도록 프롬프트에 못박는다.
"""

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enums import MenuQuadrant, MenuRole
from app.models.logs import WeeklyMenuPlan
from app.models.master import CornerMaster, MenuMaster
from app.models.stats import MenuPerformanceStats
from app.services.corner_core_layer import build_employee_corner_counts, classify_corner_core_layer
from app.services.holidays import HolidayService
from app.services.llm_client import InternalLLMClient
from app.services.menu_affinity import build_employee_menu_sets
from app.services.menu_combination import build_side_combos_for_main_menu, compute_combo_satisfaction_summary
from app.services.menu_throughput import (
    build_corner_daily_peak_share,
    build_corner_daily_throughput,
    compute_menu_throughput_summary,
    compute_peak_share_ratio,
    window_minutes,
)

_HISTORY_WINDOW_DAYS = 180  # menu_performance_stats 롤링 윈도우(6.3절)와 동일 범위


def combine_menu_multiplier(share_multiplier: float | None, throughput_ratio: float | None) -> float | None:
    """순수 함수 — 두 인기도 신호(식수 점유율 배수, 분당 처리량 비율)를
    기하평균으로 합성한다. 신호가 하나만 있으면 그것만 쓰고, 둘 다 없으면
    None(호출부가 기본 배수로 폴백)."""
    signals = [s for s in (share_multiplier, throughput_ratio) if s is not None and s > 0]
    if not signals:
        return None
    product = 1.0
    for s in signals:
        product *= s
    return product ** (1 / len(signals))


def compute_predicted_share(corner_headcounts: dict[int, float]) -> dict[int, float]:
    """순수 함수 — {corner_id: predicted_headcount}를 받아 {corner_id: 점유율}로 정규화한다."""
    total = sum(corner_headcounts.values())
    if total <= 0:
        return {corner_id: 0.0 for corner_id in corner_headcounts}
    return {corner_id: headcount / total for corner_id, headcount in corner_headcounts.items()}


def compute_expected_wait_minutes(
    predicted_headcount: float,
    effective_throughput: float | None,
    peak_share_ratio: float | None,
    peak_window_minutes: float,
) -> float | None:
    """순수 함수 — "혼잡 예상" 대기시간.

    예전엔 예상 식수 전체를 피크타임 처리량 하나로 나눠 비현실적으로 큰
    값(총 서빙 소요시간이지 개인 대기시간이 아님)이 나왔다(2026-07 실사용
    피드백). 이제는 피크타임(peak_window_minutes) 동안 처리 가능한 인원
    (= effective_throughput × peak_window_minutes)을 넘는 초과분만 대기로
    본다 — peak_share_ratio(전체 중식시간대 대비 피크타임에 실제로 몰리는
    비중, 실측)로 예상 식수 중 피크타임에 도착할 인원을 추정한다. 수요가
    피크 용량 안에 들면 0, 데이터 부족(처리량/비중 없음)이면 None.
    """
    if not effective_throughput or effective_throughput <= 0 or peak_share_ratio is None:
        return None
    expected_peak_arrivals = predicted_headcount * peak_share_ratio
    peak_capacity = effective_throughput * peak_window_minutes
    overflow = max(0.0, expected_peak_arrivals - peak_capacity)
    return round(overflow / effective_throughput, 1)


@dataclass(frozen=True)
class CoreLayerMenuSignal:
    core_employee_count: int
    core_menu_eaters: int
    non_core_employee_count: int
    non_core_menu_eaters: int


def compute_core_layer_menu_signal(
    core_employee_ids: set[str],
    all_employee_ids: set[str],
    employee_menus: dict[str, set[str]],
    menu_name: str,
) -> CoreLayerMenuSignal:
    """순수 함수 — 코어층/비코어층 각각 이 메뉴를 먹어본 적 있는 인원 수를 센다.
    확정된 배수 공식이 없으므로 이 카운트는 LLM 프롬프트에 사실로만 넘긴다."""
    non_core_ids = all_employee_ids - core_employee_ids
    core_eaters = sum(1 for e in core_employee_ids if menu_name in employee_menus.get(e, set()))
    non_core_eaters = sum(1 for e in non_core_ids if menu_name in employee_menus.get(e, set()))
    return CoreLayerMenuSignal(
        core_employee_count=len(core_employee_ids),
        core_menu_eaters=core_eaters,
        non_core_employee_count=len(non_core_ids),
        non_core_menu_eaters=non_core_eaters,
    )


def _build_summary_prompt(facts: dict[str, str]) -> str:
    return (
        "당신은 구내식당 메뉴 담당자를 돕는 분석가입니다. 아래 사실만 근거로 이번에 "
        f"'{facts['corner_name']}' 코너에서 '{facts['menu_name']}'이(가) 나올 때 어떨지 "
        "2~3문장으로 요약하세요. 사실에 없는 숫자를 지어내지 말고 정성적으로 서술하세요.\n\n"
        f"- 기존 만족도: {facts['existing_satisfaction']}\n"
        f"- 기존 평균 식수: {facts['existing_headcount']}\n"
        f"- 이 부찬 조합 과거 이력: {facts['combo_history']}\n"
        f"- 예상 점유율/식수: {facts['prediction']}\n"
        f"- 코어층 신호: {facts['core_layer']}\n"
        f"- 같은 날 경쟁 코너 현황: {facts['competition']}\n"
    )


def _fallback_summary(facts: dict[str, str]) -> str:
    return (
        f"{facts['menu_name']}은(는) 예상 식수 {facts['prediction_headcount_text']}, "
        f"예상 점유율 {facts['prediction_share_text']}로 추정됩니다. 기존 만족도는 "
        f"{facts['existing_satisfaction']}입니다. (사내 LLM 미설정 — 수치 기반 요약)"
    )


def compute_predicted_numbers(db: Session, plan_id: int) -> dict | None:
    """LLM 없이 계산 가능한 부분만 조립한다 — 기존 만족도/식수, 이 조합(메인+
    부찬)의 과거 성적, 예상 점유율/식수. plan_id가 없거나 그 행이 메인메뉴가
    아니면 None. `plan_date`/`meal_type`은 원본 파이썬 타입(date/enum) 그대로
    반환하므로, API 계층에서 JSON 직렬화 시 변환한다(이 레포의 서비스/API
    계층 분리 컨벤션과 동일 — weekly_menu_review.py도 동일한 방식)."""
    plan = db.get(WeeklyMenuPlan, plan_id)
    if plan is None or plan.menu_role != MenuRole.MAIN:
        return None

    menu = db.get(MenuMaster, plan.menu_id)
    corner = db.get(CornerMaster, plan.corner_id)

    period_end = plan.plan_date - dt.timedelta(days=1)
    period_start = period_end - dt.timedelta(days=_HISTORY_WINDOW_DAYS)

    # 1) 기존 만족도/식수 — 가장 최근 menu_performance_stats 구간
    menu_stats = (
        db.query(MenuPerformanceStats)
        .filter_by(menu_id=plan.menu_id)
        .order_by(MenuPerformanceStats.period_end.desc())
        .first()
    )

    # 2) 이 조합(메인+부찬)의 과거 성적 — 지금 이 슬롯의 실제 부찬 구성과 일치하는 것만
    current_side_ids = frozenset(
        row[0]
        for row in db.query(WeeklyMenuPlan.menu_id)
        .filter(
            WeeklyMenuPlan.plan_date == plan.plan_date,
            WeeklyMenuPlan.corner_id == plan.corner_id,
            WeeklyMenuPlan.meal_type == plan.meal_type,
            WeeklyMenuPlan.menu_role == MenuRole.SIDE,
        )
        .all()
    )
    combo_days = build_side_combos_for_main_menu(db, plan.menu_id, period_start, period_end)
    combo_summaries = compute_combo_satisfaction_summary(combo_days)
    combo_match = next((c for c in combo_summaries if c.side_menu_ids == current_side_ids), None)

    # 3) 예상 점유율/식수 — simulation.py의 baseline/배수 로직 재사용.
    # 지연 임포트: simulation.py가 analysis.py의 헬퍼를 가져다 쓰는데(_corner_id_
    # by_menu_from_meal_log), 이 파일은 analysis.py의 엔드포인트에서 호출되므로
    # 모듈 최상단에서 임포트하면 analysis → 이 파일 → simulation → analysis로
    # 순환 임포트가 생긴다. 함수 안에서 임포트하면 호출 시점엔 세 모듈 다 이미
    # 로드가 끝난 뒤라 문제없다.
    from app.api.simulation import (
        _DEFAULT_NEW_MENU_MULTIPLIER,
        _baseline_headcount,
        _menu_popularity_multiplier,
        _planned_main_menu_id,
    )

    holiday_svc = HolidayService(db)
    is_holiday = holiday_svc.is_holiday(plan.plan_date)

    share_multiplier = _menu_popularity_multiplier(db, plan.corner_id, plan.menu_id)
    throughput_days = build_corner_daily_throughput(db, plan.corner_id, period_start, period_end)
    throughput_summary = compute_menu_throughput_summary(throughput_days)
    throughput_entry = next((m for m in throughput_summary.menus if m.menu_id == plan.menu_id), None)
    throughput_ratio = (
        throughput_entry.avg_throughput / throughput_summary.overall_avg_throughput
        if throughput_entry and throughput_summary.overall_avg_throughput
        else None
    )
    combined_multiplier = combine_menu_multiplier(share_multiplier, throughput_ratio)
    target_multiplier = combined_multiplier if combined_multiplier is not None else _DEFAULT_NEW_MENU_MULTIPLIER

    corner_headcounts: dict[int, float] = {}
    for c in db.query(CornerMaster).all():
        baseline = _baseline_headcount(db, c.corner_id, plan.meal_type, is_holiday)
        if c.corner_id == plan.corner_id:
            corner_headcounts[c.corner_id] = baseline * target_multiplier
            continue
        other_planned = _planned_main_menu_id(db, c.corner_id, plan.meal_type, plan.plan_date)
        other_multiplier = (
            _menu_popularity_multiplier(db, c.corner_id, other_planned) if other_planned is not None else None
        )
        corner_headcounts[c.corner_id] = baseline * other_multiplier if other_multiplier else baseline

    predicted_shares = compute_predicted_share(corner_headcounts)
    predicted_headcount = corner_headcounts.get(plan.corner_id, 0.0)
    predicted_share = predicted_shares.get(plan.corner_id, 0.0)

    # 예상 대기시간 — 위에서 배수 합성용으로 이미 구해둔 throughput_entry/
    # throughput_summary를 재사용해 이 메뉴의 실측 분당 처리량(없으면 코너
    # 전체 평균)을 얻는다. 예상 식수 전체를 그냥 나누면(구버전) "총 서빙
    # 소요시간"이 나와 비현실적으로 크므로(2026-07 실사용 피드백), 전체
    # 중식시간대(meal_period) 대비 피크타임(peak_time)에 실제로 몰리는
    # 비중(peak_share_ratio, 실측)으로 피크 시간대 예상 인원을 추정해 피크
    # 처리 용량을 넘는 초과분만 대기로 본다.
    settings = get_settings()
    effective_throughput = (
        throughput_entry.avg_throughput if throughput_entry else throughput_summary.overall_avg_throughput
    )
    peak_count, meal_count = build_corner_daily_peak_share(db, plan.corner_id, period_start, period_end)
    peak_share_ratio = compute_peak_share_ratio(peak_count, meal_count)
    if peak_share_ratio is None:
        # 실측 데이터가 아직 없는 코너(신규 등) — 시간 비례로 폴백(v0)
        peak_share_ratio = window_minutes(settings.peak_time_start, settings.peak_time_end) / window_minutes(
            settings.meal_period_start, settings.meal_period_end
        )
    expected_wait_minutes = compute_expected_wait_minutes(
        predicted_headcount,
        effective_throughput,
        peak_share_ratio,
        window_minutes(settings.peak_time_start, settings.peak_time_end),
    )

    return {
        "plan_id": plan.id,
        "plan_date": plan.plan_date,
        "meal_type": plan.meal_type,
        "corner_id": plan.corner_id,
        "corner_name": corner.corner_name if corner else None,
        "menu_id": plan.menu_id,
        "menu_name": menu.menu_name if menu else None,
        "main_menu": {
            "menu_id": plan.menu_id,
            "menu_name": menu.menu_name if menu else None,
            "adjusted_score": menu_stats.adjusted_score if menu_stats else None,
            "total_headcount": menu_stats.total_headcount if menu_stats else None,
            "evaluation_count": menu_stats.evaluation_count if menu_stats else None,
        },
        "combo_history": (
            {
                "day_count": combo_match.day_count,
                "avg_satisfaction": combo_match.avg_satisfaction,
                "avg_headcount": round(combo_match.avg_headcount, 1),
            }
            if combo_match
            else None
        ),
        "prediction": {
            "predicted_headcount": round(predicted_headcount, 1),
            "predicted_share": round(predicted_share, 3),
            "menu_share_of_traffic": menu_stats.share_of_traffic if menu_stats else None,
            "corner_avg_share_of_traffic": (
                round(menu_stats.share_of_traffic / share_multiplier, 4)
                if menu_stats and menu_stats.share_of_traffic is not None and share_multiplier
                else None
            ),
            "throughput_ratio": round(throughput_ratio, 2) if throughput_ratio else None,
            "expected_wait_minutes": expected_wait_minutes,
        },
    }


def compute_predicted_numbers_for_period(db: Session, period_start: dt.date, period_end: dt.date) -> list[dict]:
    """그 기간의 메인메뉴 슬롯 전체(모든 코너×요일)에 대해
    `compute_predicted_numbers`를 반복 호출한다 — LLM 호출이 없어 슬롯 수만큼
    반복해도 상대적으로 빠르지만, "전체 예측 비교" 버튼을 눌렀을 때만 호출한다
    (자동 실행 아님)."""
    plan_ids = [
        row[0]
        for row in db.query(WeeklyMenuPlan.id)
        .filter(
            WeeklyMenuPlan.plan_date.between(period_start, period_end),
            WeeklyMenuPlan.menu_role == MenuRole.MAIN,
        )
        .all()
    ]
    results = []
    for plan_id in plan_ids:
        numbers = compute_predicted_numbers(db, plan_id)
        if numbers is not None:
            results.append(numbers)
    return results


async def compute_predicted_impact(db: Session, llm_client: InternalLLMClient, plan_id: int) -> dict | None:
    """오케스트레이션 — `compute_predicted_numbers` 위에 코어층/경쟁 사실 +
    LLM 정성 코멘트를 얹는다. plan_id가 없거나 메인메뉴가 아니면 None."""
    numbers = compute_predicted_numbers(db, plan_id)
    if numbers is None:
        return None

    plan_date: dt.date = numbers["plan_date"]
    meal_type = numbers["meal_type"]
    corner_id: int = numbers["corner_id"]
    corner_name = numbers["corner_name"] or ""
    menu_name = numbers["menu_name"] or ""

    period_end = plan_date - dt.timedelta(days=1)
    period_start = period_end - dt.timedelta(days=_HISTORY_WINDOW_DAYS)

    # 코어층/경쟁 사실 수집 (숫자 공식화 안 함 — LLM 프롬프트용 사실만)
    employee_corner_counts = build_employee_corner_counts(db, period_start, period_end)
    core_layer_employees = {r.employee_id for r in classify_corner_core_layer(employee_corner_counts, corner_id)}
    employee_menus = build_employee_menu_sets(db, period_start, period_end)
    core_signal = compute_core_layer_menu_signal(
        core_layer_employees, set(employee_corner_counts.keys()), employee_menus, menu_name
    )

    competing_rows = (
        db.query(WeeklyMenuPlan.menu_id, MenuMaster.menu_name, CornerMaster.corner_name)
        .join(MenuMaster, WeeklyMenuPlan.menu_id == MenuMaster.menu_id)
        .join(CornerMaster, WeeklyMenuPlan.corner_id == CornerMaster.corner_id)
        .filter(
            WeeklyMenuPlan.plan_date == plan_date,
            WeeklyMenuPlan.meal_type == meal_type,
            WeeklyMenuPlan.menu_role == MenuRole.MAIN,
            WeeklyMenuPlan.corner_id != corner_id,
        )
        .all()
    )
    competing_popular = []
    for other_menu_id, other_menu_name, other_corner_name in competing_rows:
        other_stats = (
            db.query(MenuPerformanceStats)
            .filter_by(menu_id=other_menu_id)
            .order_by(MenuPerformanceStats.period_end.desc())
            .first()
        )
        if other_stats and other_stats.quadrant_label == MenuQuadrant.POPULAR:
            competing_popular.append(f"{other_corner_name}의 {other_menu_name}(인기메뉴)")

    # LLM 코멘트 — compute_predicted_numbers가 이미 계산한 숫자를 문장으로 정리
    main_menu = numbers["main_menu"]
    combo_history = numbers["combo_history"]
    prediction = numbers["prediction"]

    existing_satisfaction_text = (
        f"{main_menu['adjusted_score']:.2f}" if main_menu["adjusted_score"] is not None else "이력 없음"
    )
    existing_headcount_text = (
        f"{main_menu['total_headcount']}" if main_menu["total_headcount"] is not None else "이력 없음"
    )
    combo_history_text = (
        f"이 조합으로 {combo_history['day_count']}일 등장, 평균 만족도 {combo_history['avg_satisfaction']:.2f}, "
        f"평균 식수 {combo_history['avg_headcount']:.1f}명"
        if combo_history and combo_history["avg_satisfaction"] is not None
        else (
            f"이 조합으로 {combo_history['day_count']}일 등장했으나 평가 없음"
            if combo_history
            else "이 정확한 부찬 조합의 과거 이력 없음"
        )
    )
    prediction_headcount_text = f"{prediction['predicted_headcount']:.1f}명"
    prediction_share_text = f"{prediction['predicted_share'] * 100:.1f}%"
    core_layer_text = (
        f"코어층 {core_signal.core_employee_count}명 중 {core_signal.core_menu_eaters}명, "
        f"비코어층 {core_signal.non_core_employee_count}명 중 {core_signal.non_core_menu_eaters}명이 "
        "이 메뉴를 먹어본 적 있음"
    )
    competition_text = ", ".join(competing_popular) if competing_popular else "같은 날 인기메뉴로 경쟁하는 코너 없음"

    facts = {
        "corner_name": corner_name,
        "menu_name": menu_name,
        "existing_satisfaction": existing_satisfaction_text,
        "existing_headcount": existing_headcount_text,
        "combo_history": combo_history_text,
        "prediction": f"식수 {prediction_headcount_text}, 점유율 {prediction_share_text}",
        "prediction_headcount_text": prediction_headcount_text,
        "prediction_share_text": prediction_share_text,
        "core_layer": core_layer_text,
        "competition": competition_text,
    }

    if llm_client.is_configured:
        summary_comment = await llm_client.chat_complete([{"role": "user", "content": _build_summary_prompt(facts)}])
    else:
        summary_comment = _fallback_summary(facts)

    return {**numbers, "summary_comment": summary_comment.strip()}

"""PRD 5.3: "메뉴 하이라이트" — 만족도 급상승/급하락, 신메뉴 초기 반응.

메뉴는 매주 나오지 않으므로 "이번 주 vs 지난 주" 같은 달력 주 단위 비교 대신,
메뉴별로 **그 메뉴가 마지막으로 나온 주 vs 그 바로 전에 나온 주**를 비교한다.
`menu_performance.py`와 같은 컨벤션으로 순수 함수 위주로 작성해 DB 없이 단위
테스트가 가능하게 한다 — 실제 meal_log 조회는 app/api/dashboard.py가 담당한다.
"""

import datetime as dt
from dataclasses import dataclass

from app.models.enums import TasteScore
from app.services.menu_performance import compute_menu_score


def week_start(date: dt.date) -> dt.date:
    return date - dt.timedelta(days=date.weekday())


@dataclass(frozen=True)
class MenuTrendEntry:
    menu_id: int
    menu_name: str
    corner_name: str | None
    recent_score: float
    prior_score: float
    delta: float
    evaluation_count: int
    recent_week: dt.date  # 이 메뉴가 마지막으로 나온 주의 월요일 — 홈 하이라이트 카드 날짜 표시용(2026-08)
    # 비교 대상이 된 직전 주의 월요일. 화면에 "4.03(7/12 주) → 4.27(8/2 주)"처럼
    # **양쪽 날짜를 다 보여달라**는 요청(2026-08) — 이미 계산하던 값을 필드로
    # 담기만 하면 되고 새 계산이 없다(§46.2에서 recent_week를 노출한 것과 동일).
    prior_week: dt.date
    prior_evaluation_count: int  # 직전 주 평가 건수 — 표본이 얼마나 되는지 같이 봐야 한다


@dataclass(frozen=True)
class NewMenuEntry:
    menu_id: int
    menu_name: str
    corner_name: str | None
    adjusted_score: float | None
    evaluation_count: int
    days_since_introduction: int


def compute_menu_satisfaction_trends(
    weekly_scores: dict[int, dict[dt.date, list[TasteScore]]],
    menu_names: dict[int, str],
    menu_corners: dict[int, str | None],
    *,
    global_avg_score: float,
    shrinkage_m: int,
    low_sample_threshold: int,
    top_n: int = 3,
) -> tuple[list[MenuTrendEntry], list[MenuTrendEntry]]:
    """weekly_scores: {menu_id: {그 메뉴가 등장한 주의 월요일: [그 주 평가 목록]}}.

    등장한 주가 2개 미만인 메뉴는 "직전 등장"이 없어 비교 대상에서 제외한다.
    returns: (델타 내림차순 상위 top_n "급상승", 델타 오름차순 상위 top_n "급하락")
    — 변화가 없거나 반대 방향인 메뉴는 각 목록에서 빠지므로 top_n보다 적을 수 있다.
    """
    entries: list[MenuTrendEntry] = []
    for menu_id, weeks in weekly_scores.items():
        week_keys = sorted(weeks.keys())
        if len(week_keys) < 2:
            continue
        prior_week, recent_week = week_keys[-2], week_keys[-1]
        prior = compute_menu_score(
            weeks[prior_week],
            global_avg_score=global_avg_score,
            shrinkage_m=shrinkage_m,
            low_sample_threshold=low_sample_threshold,
        )
        recent = compute_menu_score(
            weeks[recent_week],
            global_avg_score=global_avg_score,
            shrinkage_m=shrinkage_m,
            low_sample_threshold=low_sample_threshold,
        )
        if prior.adjusted_score is None or recent.adjusted_score is None:
            continue
        entries.append(
            MenuTrendEntry(
                menu_id=menu_id,
                menu_name=menu_names.get(menu_id, ""),
                corner_name=menu_corners.get(menu_id),
                recent_score=recent.adjusted_score,
                prior_score=prior.adjusted_score,
                delta=recent.adjusted_score - prior.adjusted_score,
                evaluation_count=recent.evaluation_count,
                recent_week=recent_week,
                prior_week=prior_week,
                prior_evaluation_count=prior.evaluation_count,
            )
        )

    rising = sorted((e for e in entries if e.delta > 0), key=lambda e: e.delta, reverse=True)[:top_n]
    falling = sorted((e for e in entries if e.delta < 0), key=lambda e: e.delta)[:top_n]
    return rising, falling


def compute_new_menu_reactions(
    new_menus: dict[int, tuple[str, str | None, dt.date]],
    scores_by_menu: dict[int, list[TasteScore]],
    *,
    global_avg_score: float,
    shrinkage_m: int,
    low_sample_threshold: int,
    today: dt.date,
) -> list[NewMenuEntry]:
    """new_menus: {menu_id: (menu_name, corner_name, 첫 등장 plan_date)} — 최근
    도입된 신메뉴 목록. scores_by_menu: {menu_id: [평가 목록]} — 그 메뉴의
    (기간 내) 평가. days_since_introduction은 도입 후 며칠째인지 — 도입은
    됐는데 계속 평가가 0건이면(변화가 없으면) 관심 유도가 필요하다는 신호."""
    results = [
        NewMenuEntry(
            menu_id=menu_id,
            menu_name=menu_name,
            corner_name=corner_name,
            adjusted_score=(
                score_result := compute_menu_score(
                    scores_by_menu.get(menu_id, []),
                    global_avg_score=global_avg_score,
                    shrinkage_m=shrinkage_m,
                    low_sample_threshold=low_sample_threshold,
                )
            ).adjusted_score,
            evaluation_count=score_result.evaluation_count,
            days_since_introduction=(today - first_plan_date).days,
        )
        for menu_id, (menu_name, corner_name, first_plan_date) in new_menus.items()
    ]
    results.sort(key=lambda e: e.days_since_introduction)
    return results

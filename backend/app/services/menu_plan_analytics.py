"""편성(weekly_menu_plan) 기준 분석 — "다음 주 뭘 빼고 뭘 넣을까" (2026-08).

식단표 8개월치가 적재되면서 처음 가능해진 분석이다. 그전엔 `weekly_menu_plan`이
최근 몇 주치뿐이라 편성 이력 자체를 분석 대상으로 쓸 수 없었다.

**기존 4분면과 축이 다르다.** `menu_performance_stats.appearance_count`는
`meal_log`의 **취식 발생 일수**다(`aggregation.py`의
`[r.eaten_at.date() for r in rows]`). 즉 편성했는데 아무도 안 먹은 메뉴는
`by_menu`에 안 들어와 4분면에서 **아예 사라진다**. 여기선 `weekly_menu_plan`
기준이라 그게 보이고, 그게 가장 강한 감편 신호다.

편성 횟수는 담당자가 **직접 통제하는 유일한 변수**다 — 만족도·식수는 결과지만
편성 횟수는 다음 주에 바꿀 수 있다.

DB를 모르는 순수 함수만 둔다. 조회는 `app/api/analysis.py`가 맡는다(레포 관례).
"""

import statistics
from dataclasses import dataclass
from enum import Enum

# 평가가 이보다 적으면 만족도를 믿고 편성을 바꾸기 어렵다.
# menu_performance의 low_sample_threshold와 같은 취지지만, 이쪽은 기간이 훨씬
# 길어(6~12개월) 기준을 조금 높게 잡는다.
DEFAULT_MIN_EVALUATIONS = 5

# 레퍼토리 집중도에서 "상위 몇 개"를 볼지.
TOP_MENU_COUNT = 5


class PlanningAction(str, Enum):
    REDUCE = "감편 검토"  # 자주 편성 + 반응 낮음
    INCREASE = "증편 후보"  # 드물게 편성 + 반응 높음
    KEEP = "주력 유지"  # 자주 + 높음
    AS_IS = "현행 유지"  # 드물게 + 낮음 — 굳이 늘릴 이유가 없다
    LOW_SAMPLE = "표본 부족"  # 평가가 적어 판단 보류
    NO_INTAKE = "취식 기록 없음"  # 편성됐는데 취식이 0 — 이름 불일치일 수도 있다


def classify_planning_action(
    plan_count: int,
    avg_satisfaction: float | None,
    evaluation_count: int,
    total_headcount: int,
    *,
    median_plan_count: float,
    median_satisfaction: float,
    min_evaluations: int = DEFAULT_MIN_EVALUATIONS,
) -> PlanningAction:
    """순수 함수 — 편성 횟수와 반응을 기간 중앙값과 비교해 편성 조정 방향을 낸다.

    기준선으로 **그 기간 전체의 중앙값**을 쓰는 건 기존 4분면
    (`aggregation.py`의 `demand_values`/`score_values` 중앙값)과 같은 방식이다.
    화면마다 다른 기준을 쓰면 담당자의 판정 감각이 어긋난다.

    판정 우선순위가 중요하다: 취식 0 → 표본 부족 → 4분면. 취식이 아예 없으면
    만족도 비교 자체가 성립하지 않고, "진짜 아무도 안 먹음"과 "메뉴명이 안 맞아
    매칭 실패"가 섞여 있어 별도 판정으로 빼서 담당자가 확인하게 한다.
    """
    if total_headcount == 0:
        return PlanningAction.NO_INTAKE
    if avg_satisfaction is None or evaluation_count < min_evaluations:
        return PlanningAction.LOW_SAMPLE

    planned_often = plan_count >= median_plan_count
    liked = avg_satisfaction >= median_satisfaction

    if planned_often and not liked:
        return PlanningAction.REDUCE
    if not planned_often and liked:
        return PlanningAction.INCREASE
    if planned_often and liked:
        return PlanningAction.KEEP
    return PlanningAction.AS_IS


def median_or_zero(values: list[float]) -> float:
    """빈 목록이면 0 — 중앙값 계산에서 예외를 던지지 않게 한다."""
    return statistics.median(values) if values else 0.0


# ---------------------------------------------------------------------------
# 코너별 레퍼토리 집중도
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepertoireStats:
    total_slots: int  # 편성 슬롯 수(같은 메뉴가 여러 번이면 여러 번 센다)
    unique_menus: int  # 고유 메뉴 종수
    top_share: float  # 상위 N개 메뉴가 전체 편성에서 차지하는 비중 (0~1)
    hhi: float  # 허핀달 지수 — 0에 가까울수록 고르게 분산, 1이면 한 메뉴뿐
    top_menus: list[tuple[str, int]]  # (메뉴명, 편성 횟수) 상위 N개


def compute_repertoire(
    plan_counts: dict[str, int], *, top_n: int = TOP_MENU_COUNT
) -> RepertoireStats:
    """순수 함수 — 메뉴명→편성 횟수에서 다양성 지표를 낸다.

    `top_share`와 `hhi`를 **둘 다** 내는 이유: 종수가 적어도 고르게 돌리면 체감
    다양성은 나쁘지 않고(HHI가 그걸 잡는다), 종수가 많아도 몇 개에 쏠리면 체감은
    단조롭다(top_share가 그걸 잡는다). 한 지표만 보면 오진한다.
    """
    total = sum(plan_counts.values())
    if total == 0:
        return RepertoireStats(
            total_slots=0, unique_menus=0, top_share=0.0, hhi=0.0, top_menus=[]
        )

    ranked = sorted(plan_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top = ranked[:top_n]
    top_share = sum(count for _, count in top) / total
    hhi = sum((count / total) ** 2 for count in plan_counts.values())

    return RepertoireStats(
        total_slots=total,
        unique_menus=len(plan_counts),
        top_share=round(top_share, 3),
        hhi=round(hhi, 4),
        top_menus=top,
    )

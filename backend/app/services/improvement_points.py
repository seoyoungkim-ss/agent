"""홈 현황 "개선 포인트" — 혼잡도/만족도/VOE 세 축에서 식당 관리자가 지금
손볼 만한 지점을 뽑는다. 세 함수 모두 이미 계산된 API 응답(dict 리스트)을
입력으로 받는 순수 함수다 — 여기서 새로 DB 쿼리를 하거나 통계를 재계산하지
않는다(`analysis.py::corner_analysis`/`menu_performance`,
`dashboard.py::_compute_voe_by_category`의 결과를 그대로 재사용).
"""

import statistics
from dataclasses import dataclass
from typing import Literal

from app.services.llm_client import InternalLLMClient


@dataclass(frozen=True)
class ImprovementPoint:
    axis: Literal["congestion", "satisfaction", "voe"]
    title: str  # "한식 코너 피크타임 혼잡" 같은 한 줄 제목
    detail: str  # 근거 수치를 담은 설명 문장
    severity: Literal["warning", "critical"]
    voe_category: str | None = None  # axis="voe"일 때만 채워짐 — 원문 코멘트 요약에 쓴다


def select_congestion_points(corners: list[dict], *, top_n: int = 2) -> list[ImprovementPoint]:
    """헤드카운트가 median 이상인 코너 중 피크타임 서브속도가 median보다 낮은
    코너를 "혼잡" 후보로 본다 — 4분면 분류(menu_performance.py::
    classify_menu_quadrant)가 쓰는 "전체 median 기준" 사상을 코너 레벨에
    그대로 적용한 것."""
    candidates = [
        c
        for c in corners
        if c.get("avg_peak_throughput_per_min") is not None and c.get("headcount_total")
    ]
    if len(candidates) < 2:
        return []

    headcount_median = statistics.median(c["headcount_total"] for c in candidates)
    throughput_median = statistics.median(c["avg_peak_throughput_per_min"] for c in candidates)

    hotspots = [
        c
        for c in candidates
        if c["headcount_total"] >= headcount_median and c["avg_peak_throughput_per_min"] < throughput_median
    ]
    hotspots.sort(key=lambda c: c["avg_peak_throughput_per_min"])

    return [
        ImprovementPoint(
            axis="congestion",
            title=f"{c['corner_name']} 코너 피크타임 혼잡",
            detail=(
                f"누적 식수 {c['headcount_total']:,}명(상위권)인데 피크타임 분당 서브가 "
                f"{c['avg_peak_throughput_per_min']:.2f}건으로 전체 중앙값({throughput_median:.2f})보다 "
                "낮습니다 — 인력 배치나 회전 방식을 점검해보세요."
            ),
            severity="warning",
        )
        for c in hotspots[:top_n]
    ]


def select_satisfaction_points(menu_rows: list[dict], *, top_n: int = 2) -> list[ImprovementPoint]:
    """수요는 높은데 만족도가 낮은("개선시급") 메뉴를 점유율 내림차순으로."""
    candidates = [m for m in menu_rows if m.get("quadrant") == "개선시급"]
    candidates.sort(key=lambda m: m.get("share_of_traffic") or 0, reverse=True)

    points = []
    for m in candidates[:top_n]:
        corner = f"({m['corner_name']}) " if m.get("corner_name") else ""
        share = m.get("share_of_traffic")
        share_text = f"점유율 {share * 100:.1f}%, " if share is not None else ""
        score = m.get("adjusted_score")
        score_text = f"{score:.2f}점" if score is not None else "평가 부족"
        points.append(
            ImprovementPoint(
                axis="satisfaction",
                title=f"{m['menu_name']} {corner}만족도 개선 필요".strip(),
                detail=(
                    f"{share_text}만족도 {score_text}(4분면: 개선시급) — 많이 찾지만 평가가 낮은 "
                    "메뉴입니다, 레시피/재료 점검을 고려하세요."
                ),
                severity="critical",
            )
        )
    return points


def select_voe_points(current: dict, prior: dict | None, *, top_n: int = 1) -> list[ImprovementPoint]:
    """VOE 카테고리 중 지난달 대비 건수 증가폭이 가장 큰 카테고리를 우선한다.
    지난달 데이터가 없으면(비교 불가) 이번 달 최다 카테고리로 대체한다.
    "기타"는 원인 진단 근거로 부적합해 후보에서 제외한다."""
    current_by_cat = {c["category"]: c["count"] for c in current.get("categories", [])}
    prior_by_cat = {c["category"]: c["count"] for c in prior["categories"]} if prior else {}

    candidates = [(cat, count) for cat, count in current_by_cat.items() if cat != "기타" and count > 0]
    if not candidates:
        return []

    if prior_by_cat:
        deltas = [(cat, count, count - prior_by_cat.get(cat, 0)) for cat, count in candidates]
        rising = sorted((d for d in deltas if d[2] > 0), key=lambda d: d[2], reverse=True)[:top_n]
        return [
            ImprovementPoint(
                axis="voe",
                title=f"'{cat}' 관련 의견 증가",
                detail=f"이번 달 {count}건 — 지난달 대비 {delta}건 늘었습니다.",
                severity="warning",
                voe_category=cat,
            )
            for cat, count, delta in rising
        ]

    cat, count = max(candidates, key=lambda c: c[1])
    return [
        ImprovementPoint(
            axis="voe",
            title=f"'{cat}' 관련 의견이 가장 많음",
            detail=f"이번 달 {count}건 — 가장 많이 언급된 카테고리입니다.",
            severity="warning",
            voe_category=cat,
        )
    ]


_VOE_SUMMARY_SAMPLE_SIZE = 10


def _build_voe_summary_prompt(category: str, comments: list[str]) -> str:
    joined = "\n".join(f"- {c}" for c in comments)
    return (
        "당신은 구내식당 운영을 돕는 분석가입니다. 아래는 이번 달 VOE(주관식 의견) 중 "
        f"'{category}' 카테고리로 분류된 코멘트 원문 일부입니다. 이 코멘트들의 주된 내용을 "
        "1~2문장으로 요약하세요. 코멘트에 없는 내용을 지어내지 마세요.\n\n"
        f"{joined}"
    )


def _fallback_voe_summary(category: str, comments: list[str]) -> str:
    sample = comments[0] if comments else ""
    return f"'{category}' 관련 코멘트 예시: \"{sample}\" 등 (사내 LLM 미설정 — 원문 예시만 표시)"


async def summarize_voe_comments(
    llm_client: InternalLLMClient, category: str, comments: list[str]
) -> str | None:
    """오케스트레이션 — VOE 카테고리의 원문 코멘트 중 일부를 LLM에 보내 주된
    내용을 1~2문장으로 요약한다. 코멘트가 없으면 None(호출부가 필드 자체를 뺀다)."""
    if not comments:
        return None
    sample = comments[:_VOE_SUMMARY_SAMPLE_SIZE]
    if llm_client.is_configured:
        prompt = _build_voe_summary_prompt(category, sample)
        summary = await llm_client.chat_complete([{"role": "user", "content": prompt}])
        return summary.strip()
    return _fallback_voe_summary(category, sample)

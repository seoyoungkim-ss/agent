"""홈 현황 "개선 필요 포인트" (2026-08 담당자 프롬프트로 전면 교체).

담당자가 준 우선순위 규칙을 그대로 구현한다 — 만족도(1순위) → VOE(2순위) →
편성·운영(3순위) → 혼잡도(4순위) 순서로 검토해 **가장 급한 이슈 하나만**
뽑는다(예전처럼 축마다 여러 건 나열하지 않는다). 어느 축에서도 유의미한
이슈가 없으면 None을 돌려주고, 화면은 "특이사항 없음"을 보여준다.

사실 수집·우선순위 판정은 전부 순수 함수(`select_priority_finding`과 그
아래 `_find_*` 헬퍼들)로 하고, LLM은 그 사실을 담당자가 지정한 4단 형식
(핵심 개선 포인트/근거/개선 방향)으로 다듬는 데만 쓴다 — 이 레포의 다른
summarize_* 함수들과 같은 패턴(§44/§77 결론). LLM 미설정·실패 시에도 같은
형식의 폴백 문구를 쓴다.

입력은 전부 이미 계산된 값이다(`analysis.py::corner_analysis`/
`menu_performance`, `dashboard.py::_compute_voe_by_category`,
`dashboard.py::_collect_planning_facts`) — 여기서 새로 DB 쿼리를 하지 않는다.
"""

import logging
import statistics
from dataclasses import dataclass
from typing import Literal

from app.services.llm_client import InternalLLMClient

logger = logging.getLogger(__name__)

Axis = Literal["satisfaction", "voe", "planning", "congestion"]

_AXIS_LABEL: dict[Axis, str] = {
    "satisfaction": "만족도",
    "voe": "VOE",
    "planning": "편성·운영",
    "congestion": "혼잡도",
}


@dataclass(frozen=True)
class PriorityFinding:
    axis: Axis
    subject: str  # 무엇이 문제인지 — 메뉴명/코너명/카테고리명 등 한 줄
    evidence: str  # 근거 수치·반복 빈도 문장
    direction_hint: str  # 개선 방향(규칙 기반 기본 문구 — LLM 프롬프트와 폴백 양쪽에 쓴다)
    voe_category: str | None = None  # axis="voe"일 때만 — 원문 코멘트 요약 조회용


# ---------------------------------------------------------------------------
# 1순위: 만족도
# ---------------------------------------------------------------------------


_CORNER_SATISFACTION_GAP_THRESHOLD = 0.3  # 5점 만점 기준, 이 이상 벌어져야 "유의미한 저조"


def _find_satisfaction_finding(corners: list[dict], menu_rows: list[dict]) -> PriorityFinding | None:
    """메뉴 4분면의 "개선시급"(수요 높고 만족도 낮음) 중 만족도가 가장 낮은
    메뉴를 우선 본다. `adjusted_score`는 이미 표본 보정(shrinkage)이 적용돼
    있고, 표본이 지나치게 적은 메뉴는 애초에 4분면 분류(LOW_SAMPLE)에서
    빠지므로(menu_performance.py::classify_menu_quadrant) 여기서 추가로
    거를 게 없다.

    "개선시급" 메뉴가 하나도 없으면 코너 단위로 내려간다 — 전체 코너 평균
    만족도보다 낮으면서, 식수가 median 이상(표본이 충분한 축)인 코너 중
    가장 낮은 곳."""
    menu_candidates = [
        m for m in menu_rows if m.get("quadrant") == "개선시급" and m.get("adjusted_score") is not None
    ]
    if menu_candidates:
        worst = min(menu_candidates, key=lambda m: m["adjusted_score"])
        corner = f"({worst['corner_name']}) " if worst.get("corner_name") else ""
        share = worst.get("share_of_traffic")
        share_text = f", 점유율 {share * 100:.1f}%" if share is not None else ""
        n = worst.get("evaluation_count") or 0
        return PriorityFinding(
            axis="satisfaction",
            subject=f"{worst['menu_name']} {corner}".strip(),
            evidence=(
                f"만족도 {worst['adjusted_score']:.2f}점(평가 {n}건{share_text}) — "
                "수요는 높은데 평가가 낮은 '개선시급' 메뉴입니다."
            ),
            direction_hint="레시피·재료·조리 방식을 점검해보세요.",
        )

    corner_candidates = [c for c in corners if c.get("avg_taste_score") is not None and c.get("headcount_total")]
    if len(corner_candidates) < 2:
        return None

    corner_avg = statistics.mean(c["avg_taste_score"] for c in corner_candidates)
    headcount_median = statistics.median(c["headcount_total"] for c in corner_candidates)
    reliable = [c for c in corner_candidates if c["headcount_total"] >= headcount_median]
    if not reliable:
        return None

    worst_corner = min(reliable, key=lambda c: c["avg_taste_score"])
    if corner_avg - worst_corner["avg_taste_score"] < _CORNER_SATISFACTION_GAP_THRESHOLD:
        # 근소한 차이는 "억지로 문제를 만들지 말라"는 원칙에 어긋난다 — 5점
        # 만점 기준 0.3점 이상 벌어졌을 때만 유의미한 저조로 본다.
        return None
    return PriorityFinding(
        axis="satisfaction",
        subject=f"{worst_corner['corner_name']} 코너",
        evidence=(
            f"평균 만족도 {worst_corner['avg_taste_score']:.2f}점 — 전체 코너 평균"
            f"({corner_avg:.2f}점)보다 낮습니다(누적 식수 {worst_corner['headcount_total']:,}명)."
        ),
        direction_hint="이 코너의 메뉴 구성이나 조리 품질을 점검해보세요.",
    )


# ---------------------------------------------------------------------------
# 2순위: VOE
# ---------------------------------------------------------------------------

_VOE_MIN_REPEAT_COUNT = 2  # "특정 의견 1건만으로 우선순위를 높이지 않는다"


def _find_voe_finding(current: dict, prior: dict | None) -> PriorityFinding | None:
    """카테고리(=유사 의견을 묶은 주제)별 건수를 본다. "기타"는 원인 진단
    근거로 부적합해 제외하고, 반복 빈도가 최소 2건 이상인 카테고리만
    후보로 삼는다 — 단발성 의견 하나로 우선순위를 올리지 않기 위해서다.
    지난달 대비 증가폭이 가장 큰 카테고리를 우선하고, 지난달 데이터가
    없으면 이번 달 최다 카테고리로 대체한다."""
    current_by_cat = {c["category"]: c["count"] for c in current.get("categories", [])}
    prior_by_cat = {c["category"]: c["count"] for c in prior["categories"]} if prior else {}

    candidates = [
        (cat, count) for cat, count in current_by_cat.items() if cat != "기타" and count >= _VOE_MIN_REPEAT_COUNT
    ]
    if not candidates:
        return None

    if prior_by_cat:
        deltas = [(cat, count, count - prior_by_cat.get(cat, 0)) for cat, count in candidates]
        rising = sorted((d for d in deltas if d[2] > 0), key=lambda d: d[2], reverse=True)
        if rising:
            cat, count, delta = rising[0]
            return PriorityFinding(
                axis="voe",
                subject=f"'{cat}' 관련 의견",
                evidence=f"이번 달 {count}건 — 지난달 대비 {delta}건 늘었습니다(여러 이용자가 반복 언급).",
                direction_hint=f"'{cat}' 관련 개선 조치를 검토해보세요.",
                voe_category=cat,
            )

    cat, count = max(candidates, key=lambda c: c[1])
    return PriorityFinding(
        axis="voe",
        subject=f"'{cat}' 관련 의견",
        evidence=f"이번 달 {count}건 — 가장 많이 반복된 카테고리입니다.",
        direction_hint=f"'{cat}' 관련 개선 조치를 검토해보세요.",
        voe_category=cat,
    )


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
    # 미설정 상태뿐 아니라 설정은 됐지만 게이트웨이 호출이 실패한 경우에도
    # 재사용하므로(2026-08) "미설정"으로 단정하지 않는 문구로 통일한다.
    sample = comments[0] if comments else ""
    return f"'{category}' 관련 코멘트 예시: \"{sample}\" 등 (사내 LLM 요약 사용 불가 — 원문 예시만 표시)"


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
        try:
            summary = await llm_client.chat_complete([{"role": "user", "content": prompt}])
            return summary.strip()
        except Exception:
            # 사내 LLM 게이트웨이 타임아웃/연결실패/오류응답이 이 예외처리 없이
            # 그대로 전파돼 "개선 필요 포인트" 카드 전체를 500으로 죽이던 문제
            # (2026-08 신고) — 조용히 원문 예시로 대체한다.
            return _fallback_voe_summary(category, sample)
    return _fallback_voe_summary(category, sample)


# ---------------------------------------------------------------------------
# 3순위: 편성·운영
# ---------------------------------------------------------------------------

_OVERUSED_TOP_N = 3
_NO_INTAKE_TOP_N = 3


def collect_planning_issues(
    *,
    overused: list[dict],
    no_intake_menus: list[dict],
    clash_slot_count: int,
) -> list[str]:
    """순수 함수 — 편성 관련 사실을 사람이 읽는 문장 목록으로.

    LLM에 넘길 재료이자, LLM이 없을 때 그대로 쓸 폴백이기도 하다.
    """
    issues: list[str] = []
    if overused:
        # 중복은 코너 안에서 판정하므로(2026-08), 어느 코너인지까지 있어야
        # 담당자가 바로 그 코너 식단을 열어볼 수 있다.
        top = overused[:_OVERUSED_TOP_N]
        names = ", ".join(
            f"{o['corner_name']} {o['menu_name']}({o['count']}회)" if o.get("corner_name")
            else f"{o['menu_name']}({o['count']}회)"
            for o in top
        )
        issues.append(f"같은 코너에 반복 편성된 메뉴: {names}")
    if no_intake_menus:
        top = no_intake_menus[:_NO_INTAKE_TOP_N]
        names = ", ".join(o["menu_name"] for o in top)
        issues.append(
            f"편성됐지만 취식 기록이 없는 메뉴 {len(no_intake_menus)}개 (예: {names}) — "
            "메뉴명 표기 불일치일 수도 있음"
        )
    if clash_slot_count > 0:
        issues.append(f"한 끼 구성에서 재료·특성이 겹치는 슬롯 {clash_slot_count}건")
    return issues


def _find_planning_finding(issues: list[str]) -> PriorityFinding | None:
    """수집된 편성 사실이 있으면 이슈 하나로 만든다 — 사전에 정의된 편성
    규칙(과다 반복/미취식/슬롯 중복)을 실제로 위반한 경우에만 신호를 낸다."""
    if not issues:
        return None
    return PriorityFinding(
        axis="planning",
        subject="주간 메뉴 편성",
        evidence=" / ".join(issues),
        direction_hint="다음 주 편성 시 위 항목을 우선 조정해보세요.",
    )


# ---------------------------------------------------------------------------
# 4순위: 혼잡도
# ---------------------------------------------------------------------------


def _find_congestion_finding(corners: list[dict]) -> PriorityFinding | None:
    """헤드카운트가 median 이상인 코너 중 피크타임 분당 서브(처리량)가
    median보다 낮은 코너를 "혼잡" 후보로 본다 — 단순 이용객 수가 아니라
    분당 서빙 수를 기준으로 삼는다."""
    candidates = [
        c for c in corners if c.get("avg_peak_throughput_per_min") is not None and c.get("headcount_total")
    ]
    if len(candidates) < 2:
        return None

    headcount_median = statistics.median(c["headcount_total"] for c in candidates)
    throughput_median = statistics.median(c["avg_peak_throughput_per_min"] for c in candidates)
    hotspots = [
        c
        for c in candidates
        if c["headcount_total"] >= headcount_median and c["avg_peak_throughput_per_min"] < throughput_median
    ]
    if not hotspots:
        return None

    worst = min(hotspots, key=lambda c: c["avg_peak_throughput_per_min"])
    return PriorityFinding(
        axis="congestion",
        subject=f"{worst['corner_name']} 코너",
        evidence=(
            f"피크타임 분당 서브 {worst['avg_peak_throughput_per_min']:.2f}건 — 전체 중앙값"
            f"({throughput_median:.2f}건)보다 낮은데 누적 식수는 {worst['headcount_total']:,}명(상위권)입니다."
        ),
        direction_hint="피크타임 인력 배치나 조리·서빙 동선을 점검해보세요.",
    )


# ---------------------------------------------------------------------------
# 우선순위 취합 — 1순위부터 순서대로, 첫 번째로 나온 이슈만 반환한다
# ---------------------------------------------------------------------------


def select_priority_finding(
    *,
    corners: list[dict],
    menu_rows: list[dict],
    current_voe: dict,
    prior_voe: dict | None,
    planning_issues: list[str],
) -> PriorityFinding | None:
    return (
        _find_satisfaction_finding(corners, menu_rows)
        or _find_voe_finding(current_voe, prior_voe)
        or _find_planning_finding(planning_issues)
        or _find_congestion_finding(corners)
    )


# ---------------------------------------------------------------------------
# 선정된 이슈를 담당자가 지정한 4단 형식으로 다듬기
# ---------------------------------------------------------------------------


def _build_priority_prompt(finding: PriorityFinding) -> str:
    return (
        "당신은 구내식당 운영 담당자를 돕는 분석가입니다. 아래 사실을 바탕으로 "
        "개선 필요 포인트를 정확히 아래 형식으로 작성하세요. 사실에 없는 내용은 "
        "지어내지 마세요. 문제를 과장하거나 단정적인 표현은 쓰지 마세요. "
        "핵심 개선 포인트는 한 문장, 근거는 아래 근거 사실을 간결하게, 개선 방향은 "
        "실행 가능한 개선 방향을 한 문장으로 씁니다.\n\n"
        f"영역: {_AXIS_LABEL[finding.axis]}\n"
        f"대상: {finding.subject}\n"
        f"근거 사실: {finding.evidence}\n"
        f"개선 방향 힌트: {finding.direction_hint}\n\n"
        "형식(각 줄 그대로 출력):\n"
        "핵심 개선 포인트: ...\n"
        "근거: ...\n"
        "개선 방향: ..."
    )


def _parse_priority_response(response: str, finding: PriorityFinding) -> dict:
    point, evidence, direction = (
        f"{finding.subject} 개선이 필요합니다.",
        finding.evidence,
        finding.direction_hint,
    )
    for line in response.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("핵심 개선 포인트:"):
            point = stripped.split(":", 1)[1].strip() or point
        elif stripped.startswith("근거:"):
            evidence = stripped.split(":", 1)[1].strip() or evidence
        elif stripped.startswith("개선 방향:"):
            direction = stripped.split(":", 1)[1].strip() or direction
    return {"area": _AXIS_LABEL[finding.axis], "point": point, "evidence": evidence, "direction": direction}


def _fallback_priority_result(finding: PriorityFinding) -> dict:
    return {
        "area": _AXIS_LABEL[finding.axis],
        "point": f"{finding.subject} 개선이 필요합니다.",
        "evidence": finding.evidence,
        "direction": finding.direction_hint,
    }


async def summarize_priority_finding(llm_client: InternalLLMClient, finding: PriorityFinding) -> dict:
    """선정된 이슈 하나를 4단 형식(area/point/evidence/direction) dict로.

    LLM 미설정·호출 실패 모두 같은 형식의 폴백으로 대체한다(§44 결론 —
    LLM 실패가 카드 전체를 죽이면 안 된다)."""
    if not llm_client.is_configured:
        return _fallback_priority_result(finding)
    try:
        response = await llm_client.chat_complete([{"role": "user", "content": _build_priority_prompt(finding)}])
        return _parse_priority_response(response, finding)
    except Exception:
        logger.exception("개선 필요 포인트 문구 다듬기 실패 — 사실 그대로 폴백")
        return _fallback_priority_result(finding)

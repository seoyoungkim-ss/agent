"""LLM이 만든 설명을 배치로 계산해 캐시에 넣는다 (2026-08).

두 가지를 담당한다:

1. **메뉴 만족도 변화 원인** — "동태찌개가 4.03 → 4.27이 됐는데 왜?"
   (부찬 조합이 바뀌었나 / 계절이 달라졌나 / 다른 코너에 밀렸나)
2. **VOE AI 브리핑** — 이번 달 주관식 의견을 주제별로 묶어 요약(§80)

편성·운영 문제 notice(과거 2번)는 §109에서 삭제됐다 — "개선 필요 포인트"가
우선순위 판정 즉시 그 결과를 LLM으로 다듬는 구조로 바뀌면서
(`improvement_points.py::summarize_priority_finding`) 이 배치 캐시를 읽는
곳이 없어졌다.

**왜 배치인가**: 화면 로드마다 LLM을 부르면 지금도 느린 화면이 더 느려진다
(§25의 판단과 같고, §50에서 "로딩되다 결과가 안 나온다"는 신고까지 겪은 뒤라
더 분명하다). `voe_clustering`/`voe_category_llm`이 이미 이 패턴이다.

**레포 관례를 따른다**(§44 결론):
- 프롬프트는 `_build_*_prompt(facts) -> str` 모듈 프라이빗 함수
- 폴백 `_fallback_*()`을 따로 두고 **미설정과 호출 실패 양쪽에 재사용**
- 사실 수집은 순수 함수로, LLM은 그 사실을 문장으로 다듬는 데만 쓴다
  (지어내지 못하게 프롬프트에 명시)
"""

import datetime as dt
import json
import logging

from sqlalchemy.orm import Session

from app.models.enums import MenuRole
from app.models.logs import MealLog, WeeklyMenuPlan
from app.models.master import MenuMaster
from app.models.stats import LlmAnalysisCache, MonthlyVoeCluster
from app.services.llm_client import InternalLLMClient

logger = logging.getLogger(__name__)

KIND_MENU_TREND = "menu_trend"
KIND_VOE_BRIEFING = "voe_briefing"


# ---------------------------------------------------------------------------
# 캐시 읽기/쓰기
# ---------------------------------------------------------------------------


def get_cached(db: Session, kind: str, subject_key: str) -> LlmAnalysisCache | None:
    """(kind, subject_key)의 **가장 최근** 분석 1건.

    ⚠️ 기간 정확 일치로 찾지 않는다 — §45에서 `menu_performance_stats`를
    `filter_by(period_start=..., period_end=...)`로 읽다가, 배치는 `period_end=어제`로
    쓰고 화면은 `period_end=오늘`로 조회해 빈 결과가 나오는 문제를 겪었다.
    대신 최신 1건을 주고, 어느 기간·언제 계산됐는지를 화면이 함께 보여준다.
    """
    return (
        db.query(LlmAnalysisCache)
        .filter(LlmAnalysisCache.kind == kind, LlmAnalysisCache.subject_key == str(subject_key))
        .order_by(LlmAnalysisCache.created_at.desc())
        .first()
    )


def save_analysis(
    db: Session,
    *,
    kind: str,
    subject_key: str,
    period_start: dt.date,
    period_end: dt.date,
    summary: str,
    facts: dict,
    keywords: list[str] | None = None,
) -> LlmAnalysisCache:
    row = LlmAnalysisCache(
        kind=kind,
        subject_key=str(subject_key),
        period_start=period_start,
        period_end=period_end,
        summary=summary,
        keywords=keywords,
        facts_json=json.dumps(facts, ensure_ascii=False, default=str),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# 1. 메뉴 만족도 변화 원인
# ---------------------------------------------------------------------------


def _recent_comments_for_menu(db: Session, menu_id: int, week_monday: dt.date, limit: int = 3) -> list[str]:
    """§77: 그 메뉴가 나온 주(월~일)의 실제 직원 코멘트 몇 개 — `dashboard.py`의
    `menu_comments` 엔드포인트와 같은 쿼리 패턴(menu_id + comment IS NOT NULL)을
    한 주 범위로 좁혀 재사용한다. 점수 변화만으로는 "왜"가 안 보이지만, 실제
    적힌 불만/칭찬은 LLM이 원인을 특정할 진짜 근거가 된다.
    """
    week_start_dt = dt.datetime.combine(week_monday, dt.time())
    week_end_dt = dt.datetime.combine(week_monday + dt.timedelta(days=7), dt.time())
    rows = (
        db.query(MealLog.comment)
        .filter(
            MealLog.menu_id == menu_id,
            MealLog.comment.isnot(None),
            MealLog.eaten_at >= week_start_dt,
            MealLog.eaten_at < week_end_dt,
        )
        .order_by(MealLog.eaten_at.desc())
        .limit(limit)
        .all()
    )
    return [comment for (comment,) in rows if comment and comment.strip()]


def _side_dishes_for_menu_week(db: Session, menu_id: int, week_monday: dt.date) -> str | None:
    """§77: 이 메뉴가 그 주에 MAIN으로 나온 슬롯(날짜·코너·식사구분)을 찾아,
    같은 슬롯의 SIDE 메뉴명을 모은다. 한 주에 여러 슬롯이 있어도 첫 슬롯만
    본다 — 대부분 주 1회 편성이라 충분하고, 여러 슬롯을 다 모으면 프롬프트가
    장황해진다."""
    week_end = week_monday + dt.timedelta(days=6)
    main_slot = (
        db.query(WeeklyMenuPlan.plan_date, WeeklyMenuPlan.corner_id, WeeklyMenuPlan.meal_type)
        .filter(
            WeeklyMenuPlan.menu_id == menu_id,
            WeeklyMenuPlan.menu_role == MenuRole.MAIN,
            WeeklyMenuPlan.plan_date.between(week_monday, week_end),
        )
        .order_by(WeeklyMenuPlan.plan_date)
        .first()
    )
    if main_slot is None:
        return None
    plan_date, corner_id, meal_type = main_slot
    side_rows = (
        db.query(MenuMaster.menu_name)
        .join(WeeklyMenuPlan, WeeklyMenuPlan.menu_id == MenuMaster.menu_id)
        .filter(
            WeeklyMenuPlan.plan_date == plan_date,
            WeeklyMenuPlan.corner_id == corner_id,
            WeeklyMenuPlan.meal_type == meal_type,
            WeeklyMenuPlan.menu_role == MenuRole.SIDE,
        )
        .all()
    )
    names = [name for (name,) in side_rows]
    return ", ".join(names) if names else None


def _build_menu_trend_prompt(facts: dict) -> str:
    direction = "올랐" if facts["delta"] > 0 else "떨어졌"
    lines = [
        f"구내식당 메뉴 '{facts['menu_name']}'의 만족도가 {direction}습니다.",
        f"- 이전 주({facts['prior_week']}): {facts['prior_score']:.2f}점",
        f"- 최근 주({facts['recent_week']}): {facts['recent_score']:.2f}점",
    ]
    if facts.get("prior_sides") or facts.get("recent_sides"):
        lines.append(
            f"- 함께 나온 부찬: 이전 {facts.get('prior_sides') or '기록 없음'} → "
            f"최근 {facts.get('recent_sides') or '기록 없음'}"
        )
    if facts.get("competing_menus"):
        lines.append(f"- 같은 날 다른 코너의 인기 메뉴: {', '.join(facts['competing_menus'])}")
    # §77: 점수·날짜만으로는 "왜"를 알 수 없어 LLM이 늘 "특정하기 어렵다"고만
    # 답하던 문제 — 실제 직원 코멘트를 근거로 준다.
    if facts.get("recent_comments") or facts.get("prior_comments"):
        recent_c = "; ".join(facts.get("recent_comments") or []) or "없음"
        prior_c = "; ".join(facts.get("prior_comments") or []) or "없음"
        lines.append(f"- 최근 주 직원 코멘트: {recent_c}")
        lines.append(f"- 이전 주 직원 코멘트: {prior_c}")
    lines.append(f"- 계절: 이전 {facts['prior_month']}월 → 최근 {facts['recent_month']}월")
    lines.append("")
    lines.append(
        "위 사실만 근거로 만족도가 왜 변했는지 한국어 두 문장 이내로 설명하세요. "
        "직원 코멘트가 있다면 그 내용을 우선 근거로 삼으세요. "
        "사실에 없는 내용은 절대 지어내지 마세요. 근거가 부족하면 "
        "'뚜렷한 원인을 특정하기 어렵다'고 쓰세요. "
        "설명 뒤 마지막 줄에 핵심 원인 관련 키워드 2~4개를 "
        "'키워드: 키워드1, 키워드2' 형식으로 덧붙이세요(원인을 특정하기 어려우면 생략)."
    )
    return "\n".join(lines)


def _fallback_menu_trend_summary(facts: dict) -> str:
    """LLM 미설정·실패 시 사실만으로 만드는 설명 — 추정은 하지 않는다."""
    direction = "상승" if facts["delta"] > 0 else "하락"
    parts = [
        f"{facts['prior_week']} 주 {facts['prior_score']:.2f}점 → "
        f"{facts['recent_week']} 주 {facts['recent_score']:.2f}점 ({direction})."
    ]
    if facts.get("prior_sides") and facts.get("recent_sides"):
        if facts["prior_sides"] != facts["recent_sides"]:
            parts.append(f"부찬 조합이 '{facts['prior_sides']}'에서 '{facts['recent_sides']}'로 바뀌었습니다.")
        else:
            parts.append("부찬 조합은 그대로였습니다.")
    if facts["prior_month"] != facts["recent_month"]:
        parts.append(f"{facts['prior_month']}월과 {facts['recent_month']}월 사이의 변화입니다.")
    if facts.get("recent_comments"):
        parts.append(f"직원 코멘트 {len(facts['recent_comments'])}건 있음(자동 요약 미설정이라 직접 확인 필요).")
    parts.append("(자동 분석 미설정 — 사실만 정리했습니다)")
    return " ".join(parts)


def _parse_menu_trend_response(response: str) -> tuple[str, list[str]]:
    """§86: 원인 설명 본문과 마지막 줄의 '키워드: ...'을 분리한다 —
    _summarize_cluster(voe_clustering.py)와 같은 델리미터 텍스트 파싱 스타일."""
    lines = response.strip().splitlines()
    keywords: list[str] = []
    body_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("키워드:"):
            keywords = [k.strip() for k in stripped.split(":", 1)[1].split(",") if k.strip()]
        else:
            body_lines.append(line)
    return "\n".join(body_lines).strip(), keywords


async def summarize_menu_trend(llm_client: InternalLLMClient, facts: dict) -> tuple[str, list[str]]:
    """사실 dict → (한국어 설명, 핵심 키워드). 실패해도 예외를 올리지 않는다."""
    if not llm_client.is_configured:
        return _fallback_menu_trend_summary(facts), []
    try:
        response = await llm_client.chat_complete(
            [{"role": "user", "content": _build_menu_trend_prompt(facts)}]
        )
        summary, keywords = _parse_menu_trend_response(response)
        return (summary or _fallback_menu_trend_summary(facts)), keywords
    except Exception:
        logger.exception("메뉴 만족도 변화 원인 분석 실패 — 폴백 문구로 대체")
        return _fallback_menu_trend_summary(facts), []


# ---------------------------------------------------------------------------
# 2. VOE AI 브리핑 (§80)
# ---------------------------------------------------------------------------
# 담당자: "네이버 리뷰 AI 브리핑처럼 주관식 VoE 요약" — 기존 `summarize_voe_comments`
# (improvement_points.py)는 카테고리 1개(가장 변화 큰 항목)의 코멘트 10개만
# 요약하는 좁은 기능이라(홈 화면 개선포인트 카드 전용), 만족도·VoE 탭에 이번
# 달 전체를 여러 테마로 묶어 요약하는 별도 브리핑을 새로 만든다.
#
# 코멘트를 새로 임베딩/재군집하지 않는다 — `cluster_monthly_voe`가 이미 그 달의
# `MonthlyVoeCluster`(테마 라벨·키워드·대표 코멘트·건수)를 계산해뒀으므로, 그
# 결과를 그대로 근거 사실로 재사용한다. 클러스터링이 아직 안 돌았으면(그 달
# `MonthlyVoeCluster`가 없으면) 브리핑도 만들 수 없다 — 호출부가 먼저 확인한다.


def _collect_voe_briefing_facts(db: Session, month_start: dt.date) -> dict:
    clusters = (
        db.query(MonthlyVoeCluster)
        .filter(MonthlyVoeCluster.period == month_start)
        .order_by(MonthlyVoeCluster.comment_count.desc())
        .all()
    )
    return {
        "month": month_start.isoformat(),
        "clusters": [
            {
                "label": c.cluster_label,
                "keywords": c.keywords or [],
                "representative_comment": c.representative_comment,
                "comment_count": c.comment_count,
            }
            for c in clusters
        ],
    }


def _build_voe_briefing_prompt(facts: dict) -> str:
    lines = [f"{facts['month'][:7]}월 구내식당 주관식 의견을 주제별로 묶은 결과입니다(건수 많은 순)."]
    for c in facts["clusters"]:
        keyword_part = f" (키워드: {', '.join(c['keywords'])})" if c["keywords"] else ""
        lines.append(f"- {c['label']}{keyword_part} — {c['comment_count']}건. 예: \"{c['representative_comment']}\"")
    lines.append("")
    lines.append(
        "위 주제들을 건수 비중을 반영해 한국어 3~4문장의 브리핑으로 요약하세요 — 네이버 리뷰 "
        "AI 브리핑처럼 이번 달 핵심을 훑어볼 수 있게 씁니다. 사실에 없는 내용은 지어내지 마세요."
    )
    return "\n".join(lines)


def _fallback_voe_briefing(facts: dict) -> str:
    """LLM 미설정·실패 시 — 건수 상위 클러스터를 불릿으로 나열."""
    if not facts["clusters"]:
        return "이번 달 주관식 의견이 없습니다."
    lines = [f"{c['label']}({c['comment_count']}건): {c['representative_comment']}" for c in facts["clusters"]]
    return " / ".join(lines) + " (자동 분석 미설정 — 사실만 정리했습니다)"


async def summarize_voe_briefing(llm_client: InternalLLMClient, facts: dict) -> str:
    if not facts["clusters"]:
        return _fallback_voe_briefing(facts)
    if not llm_client.is_configured:
        return _fallback_voe_briefing(facts)
    try:
        summary = await llm_client.chat_complete(
            [{"role": "user", "content": _build_voe_briefing_prompt(facts)}]
        )
        return summary.strip() or _fallback_voe_briefing(facts)
    except Exception:
        logger.exception("VOE AI 브리핑 요약 실패 — 폴백 문구로 대체")
        return _fallback_voe_briefing(facts)


# ---------------------------------------------------------------------------
# 배치 진입점
# ---------------------------------------------------------------------------


async def refresh_llm_analyses(
    db: Session, *, period_start: dt.date, period_end: dt.date
) -> dict[str, int]:
    """새벽 배치에서 호출 — 메뉴 만족도 변화 원인을 미리 계산한다.

    §109 이전엔 편성·운영 notice도 여기서 미리 계산해 캐시에 넣어 뒀지만,
    "개선 필요 포인트"가 우선순위 판정 직후 그 결과를 바로 LLM으로 다듬는
    구조로 바뀌면서(`improvement_points.py::summarize_priority_finding`) 그
    캐시를 읽는 곳이 없어져 이 배치 단계 자체를 삭제했다.

    지연 임포트: dashboard/analysis가 이 모듈을 임포트하므로 모듈 최상단에서
    되가져오면 순환이 된다(레포에 이미 있는 패턴 — weekly_menu_prediction 참고).
    """
    from app.api.dashboard import menu_highlights
    from app.config import get_settings

    llm_client = InternalLLMClient(get_settings())
    counts = {"menu_trend": 0}

    # 만족도가 눈에 띄게 변한 메뉴들
    try:
        # menu_highlights는 기간 인자를 안 받는다 — 자체 180일 창을 쓴다(§28).
        # 배치의 period_*는 "이 분석이 언제 기준인지" 기록용으로만 넘긴다.
        highlights = menu_highlights(db=db)
        for entry in [*highlights.get("rising", []), *highlights.get("falling", [])]:
            menu_id = entry["menu_id"]
            prior_week_date = dt.date.fromisoformat(entry["prior_week"])
            recent_week_date = dt.date.fromisoformat(entry["recent_week"])
            facts = {
                "menu_name": entry["menu_name"],
                "prior_week": entry["prior_week"],
                "recent_week": entry["recent_week"],
                "prior_score": entry["prior_score"],
                "recent_score": entry["recent_score"],
                "delta": entry["delta"],
                "prior_month": int(entry["prior_week"][5:7]),
                "recent_month": int(entry["recent_week"][5:7]),
                # §77: 이전엔 이 두 필드가 프롬프트에서만 기대되고 한 번도 채워진
                # 적이 없어(LLM이 "특정하기 어렵다"고만 답한 원인) — 이제 실제로 채운다.
                "prior_sides": _side_dishes_for_menu_week(db, menu_id, prior_week_date),
                "recent_sides": _side_dishes_for_menu_week(db, menu_id, recent_week_date),
                "prior_comments": _recent_comments_for_menu(db, menu_id, prior_week_date),
                "recent_comments": _recent_comments_for_menu(db, menu_id, recent_week_date),
            }
            summary, keywords = await summarize_menu_trend(llm_client, facts)
            save_analysis(
                db,
                kind=KIND_MENU_TREND,
                subject_key=str(entry["menu_id"]),
                period_start=period_start,
                period_end=period_end,
                summary=summary,
                facts=facts,
                keywords=keywords,
            )
            counts["menu_trend"] += 1
    except Exception:
        logger.exception("메뉴 만족도 변화 원인 배치 실패")

    return counts

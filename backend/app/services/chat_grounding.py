"""PRD 8: Agent 채팅 데이터 그라운딩.

InternalLLMClient(llm_client.py)는 tool calling을 지원하지 않는 순수 텍스트
in/out 클라이언트라, "질문에서 실제로 필요한 데이터를 미리 규칙 기반으로
판단 → DB에서 조회 → system 메시지로 프롬프트에 주입" 방식으로 그라운딩한다
(이 레포의 VOE 카테고리 분류, improvement_points.py 등과 같은 "규칙 기반
우선" 컨벤션). 새 엔드포인트를 만들지 않고 기존 라우트 함수(congestion_forecast,
corner_analysis, _compute_voe_by_category, _compute_weekly_summary,
menu_highlights)를 그대로 호출해 재사용한다.
"""

import datetime as dt

from sqlalchemy.orm import Session

from app.api.analysis import corner_analysis
from app.api.dashboard import _compute_voe_by_category, _compute_weekly_summary, menu_highlights
from app.api.simulation import congestion_forecast
from app.models.enums import MealType

# 키워드 → 카테고리 라우팅 테이블. 카테고리 하나에 여러 키워드가 매칭될 수
# 있고, 메시지 하나에 카테고리가 여러 개 매칭될 수도 있다(예: "혼잡하고
# 만족도도 낮은 코너" → congestion + satisfaction 둘 다 조회).
_KEYWORD_CATEGORIES: dict[str, tuple[str, ...]] = {
    "congestion": ("혼잡", "피크", "대기"),
    "satisfaction": ("만족도", "평가", "점수"),
    "voe": ("voe", "의견", "불만", "코멘트", "후기"),
    "headcount": ("식수", "몇명", "몇 명", "인원"),
    "new_menu": ("신메뉴", "새메뉴", "새 메뉴"),
}

GROUNDING_INSTRUCTION = (
    "다음은 카페테리아 운영 데이터베이스에서 조회한 실제 데이터입니다. "
    "답변은 이 데이터에 근거해서만 하세요. 이 데이터에 없는 내용은 추측해서 "
    "답하지 말고 '데이터가 없어 답변할 수 없습니다'라고 명확히 답하세요."
)

_SATISFACTION_WINDOW_DAYS = 30
_HEADCOUNT_TOP_N = 3
_VOE_REPRESENTATIVE_COMMENTS = 2


def route_categories(message: str) -> list[str]:
    """사용자 메시지에서 어떤 데이터 소스를 조회할지 규칙 기반으로 정한다(순수함수, DB 미접근).

    매칭되는 카테고리가 없으면 빈 리스트를 돌려주고, 호출부(build_grounded_context)가
    기본 종합 요약으로 대체한다.
    """
    lowered = message.lower()
    return [category for category, keywords in _KEYWORD_CATEGORIES.items() if any(k in lowered for k in keywords)]


def _format_congestion(db: Session) -> str:
    today = dt.date.today()
    forecast = congestion_forecast(target_date=today, meal_type=MealType.LUNCH, db=db)
    corners = sorted(forecast["corners"], key=lambda c: c["expected_peak_headcount"] or 0, reverse=True)
    lines = [f"[오늘({today.isoformat()}) 중식 혼잡 예상 — 코너별 피크타임 예상 식수/대기시간]"]
    if not corners:
        lines.append("데이터 없음")
    for c in corners:
        wait = f"{c['expected_wait_minutes']}분" if c["expected_wait_minutes"] is not None else "알 수 없음"
        lines.append(f"- {c['corner_name']}: 피크타임 예상 {c['expected_peak_headcount']}명, 예상 대기시간 {wait}")
    return "\n".join(lines)


def _format_satisfaction(db: Session) -> str:
    today = dt.date.today()
    period_start = today - dt.timedelta(days=_SATISFACTION_WINDOW_DAYS)
    corners = corner_analysis(period_start=period_start, period_end=today, db=db)
    lines = [f"[최근 {_SATISFACTION_WINDOW_DAYS}일 코너별 평균 만족도(5점 만점)/누적 식수]"]
    if not corners:
        lines.append("데이터 없음")
    for c in corners:
        score = f"{c['avg_taste_score']:.2f}" if c["avg_taste_score"] is not None else "데이터 없음"
        lines.append(f"- {c['corner_name']}: 만족도 {score}, 누적 식수 {c['headcount_total']}명")
    return "\n".join(lines)


def _format_voe(db: Session) -> str:
    today = dt.date.today()
    summary = _compute_voe_by_category(db, today.replace(day=1))
    lines = [f"[이번 달({today.strftime('%Y-%m')}) VOE 카테고리별 코멘트 건수]"]
    if summary["total_comments"] == 0:
        lines.append("데이터 없음")
    for cat in summary["categories"]:
        if cat["count"] == 0:
            continue
        lines.append(f"- {cat['category']}: {cat['count']}건")
        for comment_entry in cat["comments"][:_VOE_REPRESENTATIVE_COMMENTS]:
            lines.append(f"  예시: \"{comment_entry['comment']}\"")
    return "\n".join(lines)


def _format_headcount(db: Session) -> str:
    rows = _compute_weekly_summary(db, None, None, None)
    total = sum(r["headcount"] for r in rows)
    lines = [f"[이번 주 일자별 식수 (합계 {total}명)]"]
    if not rows:
        lines.append("데이터 없음")
    for r in rows:
        lines.append(f"- {r['date']} ({r['classification']}): {r['headcount']}명")
    return "\n".join(lines)


def _format_new_menu(db: Session) -> str:
    highlights = menu_highlights(db)
    lines = ["[최근 신메뉴 초기 반응]"]
    if not highlights["new_menus"]:
        lines.append("데이터 없음")
    for m in highlights["new_menus"]:
        score = f"{m['adjusted_score']:.2f}" if m["adjusted_score"] is not None else "평가 없음"
        lines.append(
            f"- {m['menu_name']}({m['corner_name']}): 도입 {m['days_since_introduction']}일 경과, "
            f"만족도 {score}, 평가 {m['evaluation_count']}건"
        )
    return "\n".join(lines)


_FORMATTERS_BY_CATEGORY = {
    "congestion": _format_congestion,
    "satisfaction": _format_satisfaction,
    "voe": _format_voe,
    "headcount": _format_headcount,
    "new_menu": _format_new_menu,
}


def _default_summary(db: Session) -> str:
    """질문 키워드가 어느 카테고리에도 매칭되지 않을 때의 기본 종합 요약 —
    코너별 최근 식수 상위 N개 + 이번 달 VOE 상위 카테고리."""
    today = dt.date.today()
    period_start = today - dt.timedelta(days=7)
    corners = sorted(
        corner_analysis(period_start=period_start, period_end=today, db=db),
        key=lambda c: c["headcount_total"],
        reverse=True,
    )[:_HEADCOUNT_TOP_N]
    voe = _compute_voe_by_category(db, today.replace(day=1))
    top_voe = sorted(voe["categories"], key=lambda c: c["count"], reverse=True)[:_HEADCOUNT_TOP_N]

    lines = [f"[최근 7일 식수 상위 {_HEADCOUNT_TOP_N}개 코너]"]
    if not corners:
        lines.append("데이터 없음")
    for c in corners:
        lines.append(f"- {c['corner_name']}: {c['headcount_total']}명")
    lines.append(f"\n[이번 달({today.strftime('%Y-%m')}) VOE 상위 카테고리]")
    if voe["total_comments"] == 0:
        lines.append("데이터 없음")
    for cat in top_voe:
        lines.append(f"- {cat['category']}: {cat['count']}건")
    return "\n".join(lines)


def build_grounded_context(db: Session, user_message: str) -> str:
    """질문 키워드로 관련 데이터를 조회해 system 메시지로 쓸 텍스트를 만든다.

    매칭되는 카테고리가 여러 개면 전부 조회해서 이어붙인다. 하나도 없으면
    기본 종합 요약으로 대체한다.
    """
    categories = route_categories(user_message)
    if not categories:
        sections = [_default_summary(db)]
    else:
        sections = [_FORMATTERS_BY_CATEGORY[c](db) for c in categories]
    data_block = "\n\n".join(sections)
    return f"{GROUNDING_INSTRUCTION}\n\n{data_block}"

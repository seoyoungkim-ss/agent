"""PRD 8: Agent 채팅 데이터 그라운딩.

InternalLLMClient(llm_client.py)는 tool calling을 지원하지 않는 순수 텍스트
in/out 클라이언트라, "질문에서 실제로 필요한 데이터를 미리 규칙 기반으로
판단 → DB에서 조회 → system 메시지로 프롬프트에 주입" 방식으로 그라운딩한다
(이 레포의 VOE 카테고리 분류, improvement_points.py 등과 같은 "규칙 기반
우선" 컨벤션). 새 엔드포인트를 만들지 않고 기존 라우트 함수(congestion_forecast,
corner_analysis, _compute_voe_by_category, _compute_weekly_summary,
menu_highlights, top_menus_by_headcount)를 그대로 호출해 재사용한다.

2026-07 확장: "6월 식수 top3"/"6월 가장 많이 먹은 메뉴"처럼 **기간**(몇 월)과
**의도**(top N/순위)를 파싱하지 못해 항상 "이번 주"만 보고 정렬도 안 하던
문제를 고쳤다 — `_extract_month_range`/`_extract_top_n`/`_wants_ranking`
(모두 순수함수)로 메시지에서 기간·랭킹 의도를 뽑아 포매터에 반영한다.
"""

import calendar
import datetime as dt
import re

from sqlalchemy.orm import Session

from app.api.analysis import corner_analysis, top_menus_by_headcount
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
    # "메뉴"만 넣으면 다른 카테고리와 과도하게 겹치므로, "많이 먹은 메뉴"류
    # 구문 단위로만 매칭한다(new_menu와도 겹치지 않게 신메뉴 표현은 제외).
    "menu_ranking": ("많이 먹은", "인기 메뉴", "메뉴 순위", "가장 인기", "top 메뉴", "탑 메뉴"),
}

GROUNDING_INSTRUCTION = (
    "다음은 카페테리아 운영 데이터베이스에서 조회한 실제 데이터입니다. "
    "답변은 이 데이터에 근거해서만 하세요. 이 데이터에 없는 내용은 추측해서 "
    "답하지 말고 '데이터가 없어 답변할 수 없습니다'라고 명확히 답하세요."
)

_SATISFACTION_WINDOW_DAYS = 30
_MENU_RANKING_WINDOW_DAYS = 30
_HEADCOUNT_TOP_N = 3
_VOE_REPRESENTATIVE_COMMENTS = 2
_DEFAULT_RANKING_TOP_N = 5

_MONTH_PATTERN = re.compile(r"(\d{1,2})\s*월")
_TOP_N_PATTERN = re.compile(r"(?:top|탑|상위)\s*(\d+)|(\d+)\s*위", re.IGNORECASE)
_RANKING_KEYWORDS = ("top", "탑", "순위", "가장 많이", "가장 적게", "인기")


def route_categories(message: str) -> list[str]:
    """사용자 메시지에서 어떤 데이터 소스를 조회할지 규칙 기반으로 정한다(순수함수, DB 미접근).

    매칭되는 카테고리가 없으면 빈 리스트를 돌려주고, 호출부(build_grounded_context)가
    기본 종합 요약으로 대체한다.
    """
    lowered = message.lower()
    return [category for category, keywords in _KEYWORD_CATEGORIES.items() if any(k in lowered for k in keywords)]


def _extract_month_range(message: str) -> tuple[dt.date, dt.date] | None:
    """메시지에서 "N월"/"지난달"/"이번달" 같은 기간 표현을 (그 달의 시작일,
    말일)로 변환한다(순수함수, `dt.date.today()`만 참조). 매칭이 없으면 None
    — 호출부가 각자의 기본 기간(이번 주/최근 N일 등)을 쓴다.

    "N월"이 오늘 기준 이번 달보다 크면 작년으로 간주한다 — "가장 최근에 지난
    그 달"이 자연스러운 해석이기 때문(예: 7월에 "12월"은 작년 12월).
    """
    today = dt.date.today()
    if "지난달" in message or "저번달" in message:
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - dt.timedelta(days=1)
        return last_month_end.replace(day=1), last_month_end
    if "이번달" in message or "이번 달" in message:
        return today.replace(day=1), today

    match = _MONTH_PATTERN.search(message)
    if not match:
        return None
    month = int(match.group(1))
    if not 1 <= month <= 12:
        return None
    year = today.year if month <= today.month else today.year - 1
    start = dt.date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = dt.date(year, month, last_day)
    return start, end


def _extract_top_n(message: str, default: int = _DEFAULT_RANKING_TOP_N) -> int:
    """"top3"/"탑3"/"상위 3"/"3위" 같은 표현에서 N을 뽑는다(순수함수)."""
    match = _TOP_N_PATTERN.search(message.lower())
    if not match:
        return default
    number = match.group(1) or match.group(2)
    return int(number) if number else default


def _wants_ranking(message: str) -> bool:
    """"top"/"탑"/"순위"/"가장 많이"/"가장 적게"/"인기" 등 랭킹 의도 키워드 매칭(순수함수)."""
    lowered = message.lower()
    return any(k in lowered for k in _RANKING_KEYWORDS)


def _format_congestion(db: Session, message: str) -> str:
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


def _format_satisfaction(db: Session, message: str) -> str:
    month_range = _extract_month_range(message)
    if month_range:
        period_start, period_end = month_range
        label = period_start.strftime("%Y-%m")
    else:
        period_end = dt.date.today()
        period_start = period_end - dt.timedelta(days=_SATISFACTION_WINDOW_DAYS)
        label = f"최근 {_SATISFACTION_WINDOW_DAYS}일"
    corners = corner_analysis(period_start=period_start, period_end=period_end, db=db)
    lines = [f"[{label} 코너별 평균 만족도(5점 만점)/누적 식수]"]
    if not corners:
        lines.append("데이터 없음")
    for c in corners:
        score = f"{c['avg_taste_score']:.2f}" if c["avg_taste_score"] is not None else "데이터 없음"
        lines.append(f"- {c['corner_name']}: 만족도 {score}, 누적 식수 {c['headcount_total']}명")
    return "\n".join(lines)


def _format_voe(db: Session, message: str) -> str:
    month_range = _extract_month_range(message)
    period = month_range[0] if month_range else dt.date.today().replace(day=1)
    summary = _compute_voe_by_category(db, period)
    lines = [f"[{period.strftime('%Y-%m')} VOE 카테고리별 코멘트 건수]"]
    if summary["total_comments"] == 0:
        lines.append("데이터 없음")
    for cat in summary["categories"]:
        if cat["count"] == 0:
            continue
        lines.append(f"- {cat['category']}: {cat['count']}건")
        for comment_entry in cat["comments"][:_VOE_REPRESENTATIVE_COMMENTS]:
            lines.append(f"  예시: \"{comment_entry['comment']}\"")
    return "\n".join(lines)


def _format_headcount(db: Session, message: str) -> str:
    month_range = _extract_month_range(message)
    if month_range:
        start, end = month_range
        rows = _compute_weekly_summary(db, start, end, None)
        label = start.strftime("%Y-%m")
    else:
        rows = _compute_weekly_summary(db, None, None, None)
        label = "이번 주"

    if _wants_ranking(message):
        top_n = _extract_top_n(message)
        rows = sorted(rows, key=lambda r: r["headcount"], reverse=True)[:top_n]
        header = f"[{label} 식수 상위 {len(rows)}일]"
    else:
        header = f"[{label} 일자별 식수 (합계 {sum(r['headcount'] for r in rows)}명)]"

    lines = [header]
    if not rows:
        lines.append("데이터 없음")
    for r in rows:
        lines.append(f"- {r['date']} ({r['classification']}): {r['headcount']}명")
    return "\n".join(lines)


def _format_new_menu(db: Session, message: str) -> str:
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


def _format_menu_ranking(db: Session, message: str) -> str:
    month_range = _extract_month_range(message)
    if month_range:
        period_start, period_end = month_range
        label = period_start.strftime("%Y-%m")
    else:
        period_end = dt.date.today()
        period_start = period_end - dt.timedelta(days=_MENU_RANKING_WINDOW_DAYS)
        label = f"최근 {_MENU_RANKING_WINDOW_DAYS}일"
    top_n = _extract_top_n(message)
    rows = top_menus_by_headcount(period_start=period_start, period_end=period_end, top_n=top_n, db=db)
    lines = [f"[{label} 취식 건수 상위 {top_n}개 메뉴]"]
    if not rows:
        lines.append("데이터 없음")
    for r in rows:
        lines.append(f"- {r['menu_name']}: {r['headcount']}건")
    return "\n".join(lines)


_FORMATTERS_BY_CATEGORY = {
    "congestion": _format_congestion,
    "satisfaction": _format_satisfaction,
    "voe": _format_voe,
    "headcount": _format_headcount,
    "new_menu": _format_new_menu,
    "menu_ranking": _format_menu_ranking,
}


def _default_summary(db: Session, message: str) -> str:
    """질문 키워드가 어느 카테고리에도 매칭되지 않을 때의 기본 종합 요약 —
    코너별 최근 식수 상위 N개 + VOE 상위 카테고리(메시지에 월이 있으면 그
    달, 없으면 최근 7일/이번 달 기준)."""
    month_range = _extract_month_range(message)
    if month_range:
        period_start, period_end = month_range
        voe_period = period_start
        headcount_label = period_start.strftime("%Y-%m")
    else:
        period_end = dt.date.today()
        period_start = period_end - dt.timedelta(days=7)
        voe_period = period_end.replace(day=1)
        headcount_label = "최근 7일"

    corners = sorted(
        corner_analysis(period_start=period_start, period_end=period_end, db=db),
        key=lambda c: c["headcount_total"],
        reverse=True,
    )[:_HEADCOUNT_TOP_N]
    voe = _compute_voe_by_category(db, voe_period)
    top_voe = sorted(voe["categories"], key=lambda c: c["count"], reverse=True)[:_HEADCOUNT_TOP_N]

    lines = [f"[{headcount_label} 식수 상위 {_HEADCOUNT_TOP_N}개 코너]"]
    if not corners:
        lines.append("데이터 없음")
    for c in corners:
        lines.append(f"- {c['corner_name']}: {c['headcount_total']}명")
    lines.append(f"\n[{voe_period.strftime('%Y-%m')} VOE 상위 카테고리]")
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
        sections = [_default_summary(db, user_message)]
    else:
        sections = [_FORMATTERS_BY_CATEGORY[c](db, user_message) for c in categories]
    data_block = "\n\n".join(sections)
    return f"{GROUNDING_INSTRUCTION}\n\n{data_block}"

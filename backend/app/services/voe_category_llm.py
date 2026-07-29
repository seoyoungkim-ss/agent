"""PRD 5.2/5.3: 월간 VOE 고정 분류(맛/간/위생/서비스)를 LLM으로 계산한다.

`voe_category.py`의 키워드 규칙 대신, 사내 LLM이 코멘트에서 키워드를 뽑고 그
키워드를 근거로 카테고리를 매기는 방식으로 바꿔달라는 요청(2026-07)에 따른
구현이다. 매달 배치로 한 번만 계산해 `meal_log.voe_categories`/`voe_keywords`에
저장한다(누적) — `voe_clustering.py`(월간 자유형 클러스터)와 같은 실행 방식.
홈 화면은 저장된 값만 읽으므로 요청마다 LLM을 부르지 않는다.

사내 LLM이 설정 안 된 환경에서는 기존 규칙 기반(`voe_category.py`)으로 대체
저장해 배선만 검증한다 — 실제 분류 품질은 사내 LLM 연동 후 확인해야 한다.
"""

import calendar
import datetime as dt

from sqlalchemy.orm import Session

from app.models.logs import MealLog
from app.services.llm_client import InternalLLMClient
from app.services.voe_category import OTHER_CATEGORY, VOE_CATEGORIES, classify_voe_categories

_BATCH_SIZE = 30


async def classify_monthly_voe_via_llm(
    db: Session, period_month: dt.date, llm_client: InternalLLMClient
) -> int:
    """해당 월의 meal_log.comment를 LLM으로 분류해 voe_categories/voe_keywords에
    upsert한다. returns: 분류된 코멘트 수."""
    month_start = period_month.replace(day=1)
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    month_end_exclusive = dt.datetime.combine(
        month_start.replace(day=last_day) + dt.timedelta(days=1), dt.time()
    )
    month_start_dt = dt.datetime.combine(month_start, dt.time())

    logs = [
        log
        for log in (
            db.query(MealLog)
            .filter(
                MealLog.eaten_at >= month_start_dt,
                MealLog.eaten_at < month_end_exclusive,
                MealLog.comment.isnot(None),
            )
            .all()
        )
        if log.comment and log.comment.strip()
    ]
    if not logs:
        return 0

    if not llm_client.is_configured:
        # 사내 LLM 미설정 — 기존 규칙 기반으로 대체 저장(배선 검증용, 키워드는 없음).
        for log in logs:
            log.voe_categories = classify_voe_categories(log.comment) or [OTHER_CATEGORY]
            log.voe_keywords = None
        db.commit()
        return len(logs)

    classified = 0
    for i in range(0, len(logs), _BATCH_SIZE):
        batch = logs[i : i + _BATCH_SIZE]
        results = await _classify_batch(llm_client, [log.comment for log in batch])
        for log, (categories, keywords) in zip(batch, results):
            log.voe_categories = categories or [OTHER_CATEGORY]
            log.voe_keywords = keywords or None
            classified += 1
        db.commit()
    return classified


async def _classify_batch(
    llm_client: InternalLLMClient, comments: list[str]
) -> list[tuple[list[str], list[str]]]:
    categories_str = "/".join(VOE_CATEGORIES)
    prompt = (
        "다음은 사내 카페테리아 이용자 의견입니다. 각 의견마다 번호에 맞춰 정확히\n"
        "'번호. 카테고리: A,B | 키워드: k1,k2' 형식으로만 답하세요(한 줄에 하나씩).\n"
        f"카테고리는 반드시 {categories_str} 중에서만 골라 쉼표로 구분해 여러 개 쓸 수 있고, "
        f"해당 사항이 없으면 '{OTHER_CATEGORY}'라고만 쓰세요. "
        "키워드는 그 카테고리로 판단한 근거가 된 짧은 표현 1~3개, 없으면 '없음'.\n\n"
        + "\n".join(f"{idx + 1}. {c}" for idx, c in enumerate(comments))
    )
    response = await llm_client.chat_complete([{"role": "user", "content": prompt}])
    return _parse_batch_response(response, len(comments))


def _parse_batch_response(response: str, expected_count: int) -> list[tuple[list[str], list[str]]]:
    """LLM 응답 파싱 — 형식이 어긋난 줄은 조용히 건너뛰고, 못 찾은 항목은 빈 값으로
    둔다(호출부가 이 경우 "기타"로 대체)."""
    results: dict[int, tuple[list[str], list[str]]] = {}
    for line in response.splitlines():
        line = line.strip()
        if not line or "." not in line or "카테고리" not in line:
            continue
        idx_str, _, rest = line.partition(".")
        idx_str = idx_str.strip()
        if not idx_str.isdigit():
            continue
        idx = int(idx_str)
        cat_part, _, kw_part = rest.partition("|")
        categories = [
            c.strip()
            for c in cat_part.split("카테고리:", 1)[-1].split(",")
            if c.strip() and c.strip() in VOE_CATEGORIES
        ]
        keywords = [
            k.strip()
            for k in kw_part.split("키워드:", 1)[-1].split(",")
            if k.strip() and k.strip() not in ("없음", "-")
        ]
        results[idx] = (categories, keywords)

    return [results.get(i + 1, ([], [])) for i in range(expected_count)]

"""PRD 5.2 / 8: 월간 VOE(주관식 의견) 클러스터링 — 사내 LLM 채팅 기반 그룹핑.

monthly_voe_cluster 테이블에 클러스터별 대표 코멘트/건수/키워드를 저장한다.

§86: 원래는 사내 LLM 임베딩 API(embed()) + KMeans로 클러스터링했으나, 임베딩
엔드포인트 경로가 실제 게이트웨이에서 검증된 적이 없어(§29) 404가 났고
dashboard.py가 이를 502로 감싸 보여주는 문제가 있었다. 이미 검증된
chat_complete() 하나로 LLM이 직접 코멘트를 그룹핑하도록 바꿔 임베딩 API
의존성 자체를 없앴다. llm_client.py의 embed()/_mock_embedding()은 범용
클라이언트 API로 그대로 남겨둔다 — 이번 문제의 원인은 그 메서드가 아니라
그 메서드를 부르던 유일한 호출부였다.
"""

import calendar
import datetime as dt

from sqlalchemy.orm import Session

from app.models.logs import MealLog
from app.models.stats import MonthlyVoeCluster
from app.services.llm_client import InternalLLMClient

_MAX_COMMENTS_DEFAULT = 150


async def cluster_monthly_voe(
    db: Session,
    period_month: dt.date,
    llm_client: InternalLLMClient,
    *,
    max_clusters: int = 5,
    max_comments: int = _MAX_COMMENTS_DEFAULT,
) -> int:
    month_start = period_month.replace(day=1)
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    month_end_exclusive = dt.datetime.combine(
        month_start.replace(day=last_day) + dt.timedelta(days=1), dt.time()
    )
    month_start_dt = dt.datetime.combine(month_start, dt.time())

    comments = [
        c
        for (c,) in db.query(MealLog.comment)
        .filter(
            MealLog.eaten_at >= month_start_dt,
            MealLog.eaten_at < month_end_exclusive,
            MealLog.comment.isnot(None),
        )
        .all()
        if c and c.strip()
    ]
    if not comments:
        return 0

    # 코멘트가 너무 많으면 프롬프트 길이가 감당 안 되므로 앞에서부터 자른다
    # (전수가 아니라 표본 — 그 달 코멘트 규모를 대략 대표한다는 가정).
    sample = comments[:max_comments]

    prompt = _build_cluster_prompt(sample, max_clusters)
    response = await llm_client.chat_complete([{"role": "user", "content": prompt}])
    clusters = _parse_cluster_response(response, sample)
    if not clusters:
        raise ValueError("사내 LLM 응답에서 클러스터를 하나도 파싱하지 못했습니다.")

    # 기존 이번 달 클러스터 결과는 지우고 다시 쓴다 (배치 재계산).
    db.query(MonthlyVoeCluster).filter(MonthlyVoeCluster.period == month_start).delete()

    for cluster_label, representative, comment_count, keywords in clusters:
        db.add(
            MonthlyVoeCluster(
                period=month_start,
                cluster_label=cluster_label,
                representative_comment=representative,
                comment_count=comment_count,
                keywords=keywords,
            )
        )

    db.commit()
    return len(clusters)


def _build_cluster_prompt(sample: list[str], max_clusters: int) -> str:
    numbered = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(sample))
    return (
        "다음은 사내 카페테리아 이용자들이 남긴 주관식 의견입니다. 번호가 붙어 있습니다.\n"
        f"이 의견들을 비슷한 주제끼리 최대 {max_clusters}개 그룹으로 나누세요. "
        "그룹마다 아래 형식으로 답하고, 그룹과 그룹 사이는 빈 줄로 구분하세요:\n"
        "라벨: (짧은 주제 라벨, 10자 내외)\n"
        "키워드: 키워드1, 키워드2, 키워드3\n"
        "대표코멘트: (이 그룹을 가장 잘 대표하는 의견 원문 그대로)\n"
        "번호: (이 그룹에 속하는 의견 번호를 콤마로, 예: 1,4,7,12)\n\n"
        + numbered
    )


def _parse_cluster_response(
    response: str, sample: list[str]
) -> list[tuple[str, str, int, list[str]]]:
    blocks = [b for b in response.split("\n\n") if b.strip()]
    clusters: list[tuple[str, str, int, list[str]]] = []
    for block in blocks:
        label = "미분류"
        keywords: list[str] = []
        representative = ""
        numbers: list[int] = []
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("라벨:"):
                label = line.split(":", 1)[1].strip() or label
            elif line.startswith("키워드:"):
                keywords = [k.strip() for k in line.split(":", 1)[1].split(",") if k.strip()]
            elif line.startswith("대표코멘트:"):
                representative = line.split(":", 1)[1].strip()
            elif line.startswith("번호:"):
                for tok in line.split(":", 1)[1].split(","):
                    tok = tok.strip()
                    if not tok.isdigit():
                        continue
                    idx = int(tok)
                    if 1 <= idx <= len(sample):
                        numbers.append(idx)

        if not numbers:
            continue
        comment_count = len(numbers)
        if not representative:
            representative = sample[numbers[0] - 1]
        clusters.append((label, representative, comment_count, keywords))

    return clusters

"""PRD 5.2 / 8: 월간 VOE(주관식 의견) 클러스터링 — 사내 LLM 임베딩 + KMeans.

monthly_voe_cluster 테이블에 클러스터별 대표 코멘트/건수/키워드를 저장한다.
사내 LLM이 아직 설정되지 않은 환경(로컬 개발/데모)에서는 llm_client의 모의
임베딩·모의 응답으로 배선만 검증할 수 있다 — 실제 군집 품질은 사내 LLM 연동
후 확인해야 한다.
"""

import calendar
import datetime as dt

import numpy as np
from sklearn.cluster import KMeans
from sqlalchemy.orm import Session

from app.models.logs import MealLog
from app.models.stats import MonthlyVoeCluster
from app.services.llm_client import InternalLLMClient


async def cluster_monthly_voe(
    db: Session,
    period_month: dt.date,
    llm_client: InternalLLMClient,
    *,
    max_clusters: int = 5,
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

    n_clusters = min(max_clusters, len(comments))
    embeddings = await llm_client.embed(comments)
    matrix = np.array(embeddings, dtype=float)

    kmeans = KMeans(n_clusters=n_clusters, n_init="auto", random_state=42)
    labels = kmeans.fit_predict(matrix)

    # 기존 이번 달 클러스터 결과는 지우고 다시 쓴다 (배치 재계산).
    db.query(MonthlyVoeCluster).filter(MonthlyVoeCluster.period == month_start).delete()

    for cluster_id in range(n_clusters):
        cluster_comments = [c for c, label in zip(comments, labels) if label == cluster_id]
        if not cluster_comments:
            continue
        cluster_vectors = matrix[labels == cluster_id]
        centroid = cluster_vectors.mean(axis=0)
        distances = np.linalg.norm(cluster_vectors - centroid, axis=1)
        representative = cluster_comments[int(np.argmin(distances))]

        cluster_label, keywords = await _summarize_cluster(llm_client, cluster_comments)

        db.add(
            MonthlyVoeCluster(
                period=month_start,
                cluster_label=cluster_label,
                representative_comment=representative,
                comment_count=len(cluster_comments),
                keywords=keywords,
            )
        )

    db.commit()
    return n_clusters


async def _summarize_cluster(
    llm_client: InternalLLMClient, comments: list[str]
) -> tuple[str, list[str]]:
    sample = comments[:20]
    prompt = (
        "다음은 사내 카페테리아 이용자들이 남긴 주관식 의견입니다. "
        "이 의견들을 아우르는 짧은 주제 라벨(10자 내외)과 핵심 키워드 3~5개를 "
        "'라벨: ...\\n키워드: 키워드1, 키워드2, ...' 형식으로 답하세요.\n\n"
        + "\n".join(f"- {c}" for c in sample)
    )
    response = await llm_client.chat_complete([{"role": "user", "content": prompt}])

    label = "미분류"
    keywords: list[str] = []
    for line in response.splitlines():
        if line.startswith("라벨:"):
            label = line.split(":", 1)[1].strip() or label
        elif line.startswith("키워드:"):
            keywords = [k.strip() for k in line.split(":", 1)[1].split(",") if k.strip()]
    return label, keywords

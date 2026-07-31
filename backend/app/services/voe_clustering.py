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
    # 사내 LLM 임베딩 API가 응답 개수/차원을 어긋나게 돌려주면 np.array()가
    # ragged sequence로 알아보기 힘든 예외를 던진다 — 여기서 먼저 검증해
    # 명확한 원인을 남긴다(2026-07, 500 에러 재현 조사 중 발견한 방어 지점).
    if len(embeddings) != len(comments):
        raise ValueError(
            f"임베딩 개수({len(embeddings)})가 코멘트 개수({len(comments)})와 다릅니다 — "
            "사내 LLM 임베딩 API 응답을 확인하세요."
        )
    embedding_dim = len(embeddings[0]) if embeddings else 0
    if any(len(e) != embedding_dim for e in embeddings):
        raise ValueError("사내 LLM 임베딩 API가 반환한 벡터들의 차원이 서로 다릅니다.")
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

        # 라벨/키워드는 부가 정보라(핵심인 클러스터 배정 자체는 이미 KMeans로
        # 끝남) 사내 LLM 요약 호출이 실패해도 전체 재계산을 실패시키지 않고
        # "미분류"로 대체한다 — _summarize_cluster 파싱 실패 시의 기존 기본값
        # (label = "미분류")과 같은 성격의 폴백을 호출 실패에도 확장한 것.
        try:
            cluster_label, keywords = await _summarize_cluster(llm_client, cluster_comments)
        except Exception:
            cluster_label, keywords = "미분류", []

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

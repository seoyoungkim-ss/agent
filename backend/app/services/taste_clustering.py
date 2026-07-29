"""PRD 6.1: 사번별 취향 벡터를 K-means로 묶어 "취향 군집" 요약을 만든다.

개별 사번 조회(6.1의 개인 취향 벡터)만으로는 전체 경향을 한눈에 보기 어렵다는
문제의식에서, employee_taste_profile.profile_vector들을 군집화해 몇 개의 취향
그룹(예: "매운맛·국물 선호형")으로 요약한다. 라벨링은 순수 규칙 기반이다 —
food_vector가 이미 구조화된 수치 벡터라 VOE(자유 텍스트) 클러스터링과 달리 사내
LLM 없이도 결정론적으로 이름을 붙일 수 있다.
"""

import datetime as dt
import statistics
from collections import Counter
from dataclasses import dataclass

import numpy as np
from sklearn.cluster import KMeans
from sqlalchemy.orm import Session

from app.models.enums import TASTE_SCORE_POINTS
from app.models.logs import MealLog
from app.models.master import CornerMaster, MenuMaster
from app.models.stats import EmployeeTasteProfile, TasteCluster
from app.services.food_vector import FOOD_VECTOR_DIMENSIONS, FOOD_VECTOR_LABELS_KO

# 이 값보다 평균에서 튀어야 "선호형" 라벨에 그 차원 이름을 넣는다(0~1 스케일 기준).
_LABEL_DEVIATION_THRESHOLD = 0.12
_LABEL_MAX_DIMENSIONS = 2
_BALANCED_LABEL = "균형형"


@dataclass(frozen=True)
class ClusteringResult:
    labels: list[int]  # 입력 벡터 순서와 대응하는 cluster index
    centroids: list[list[float]]


def cluster_vectors(vectors: list[list[float]], k: int) -> ClusteringResult:
    """순수 K-means 래퍼 — DB 없이 테스트 가능."""
    matrix = np.array(vectors, dtype=float)
    kmeans = KMeans(n_clusters=k, n_init="auto", random_state=42)
    labels = kmeans.fit_predict(matrix)
    return ClusteringResult(labels=labels.tolist(), centroids=kmeans.cluster_centers_.tolist())


def generate_cluster_label(
    centroid: list[float],
    global_mean: list[float],
    *,
    dimensions: list[str] = FOOD_VECTOR_DIMENSIONS,
    labels_ko: dict[str, str] = FOOD_VECTOR_LABELS_KO,
    threshold: float = _LABEL_DEVIATION_THRESHOLD,
    max_dimensions: int = _LABEL_MAX_DIMENSIONS,
) -> str:
    """centroid가 전체 평균보다 뚜렷이 높은 차원 1~2개로 "OO·OO 선호형" 라벨을 만든다.

    튀는 차원이 없으면(전부 평균과 비슷하면) "균형형"으로 표시한다.
    """
    deviations = [(dimensions[i], centroid[i] - global_mean[i]) for i in range(len(dimensions))]
    standout = sorted(
        (d for d in deviations if d[1] >= threshold), key=lambda d: d[1], reverse=True
    )[:max_dimensions]
    if not standout:
        return _BALANCED_LABEL
    names = [labels_ko.get(dim, dim) for dim, _ in standout]
    return "·".join(names) + " 선호형"


def compute_taste_clusters(
    db: Session, *, k: int = 5, min_total_employees: int | None = None
) -> int:
    """PRD 6.1: 전체 취향 프로필을 재군집화해 taste_cluster를 다시 쓴다.

    표본이 군집 수 대비 너무 적으면(기본: k*2 미만) 의미 있는 군집이 안 나오므로
    건너뛴다(반환값 0). 반환값은 실제로 생성된 군집 수.
    """
    min_total_employees = min_total_employees if min_total_employees is not None else k * 2
    profiles = db.query(EmployeeTasteProfile).all()
    if len(profiles) < min_total_employees:
        return 0

    vectors = [list(p.profile_vector) for p in profiles]
    employee_ids = [p.employee_id for p in profiles]
    result = cluster_vectors(vectors, k)
    global_mean = np.array(vectors, dtype=float).mean(axis=0).tolist()

    members_by_cluster: dict[int, list[str]] = {}
    for employee_id, cluster_idx in zip(employee_ids, result.labels):
        members_by_cluster.setdefault(cluster_idx, []).append(employee_id)

    menu_names = dict(db.query(MenuMaster.menu_id, MenuMaster.menu_name).all())
    corner_names = dict(db.query(CornerMaster.corner_id, CornerMaster.corner_name).all())

    # 기존 배치 결과 정리: FK 참조부터 끊고(SET NULL) 지운다.
    db.query(EmployeeTasteProfile).update({EmployeeTasteProfile.cluster_id: None})
    db.query(TasteCluster).delete()
    db.flush()

    created = 0
    for cluster_idx, member_ids in members_by_cluster.items():
        logs = db.query(MealLog).filter(MealLog.employee_id.in_(member_ids)).all()

        menu_counter = Counter(menu_names[l.menu_id] for l in logs if l.menu_id in menu_names)
        corner_counter = Counter(
            corner_names[l.corner_id] for l in logs if l.corner_id in corner_names
        )
        scores = [TASTE_SCORE_POINTS[l.taste_score] for l in logs if l.taste_score is not None]

        cluster = TasteCluster(
            computed_at=dt.datetime.utcnow(),
            cluster_index=cluster_idx,
            label=generate_cluster_label(result.centroids[cluster_idx], global_mean),
            size=len(member_ids),
            centroid_vector=result.centroids[cluster_idx],
            avg_satisfaction=statistics.fmean(scores) if scores else None,
            top_menus=[name for name, _ in menu_counter.most_common(5)],
            dominant_corner=corner_counter.most_common(1)[0][0] if corner_counter else None,
        )
        db.add(cluster)
        db.flush()

        db.query(EmployeeTasteProfile).filter(
            EmployeeTasteProfile.employee_id.in_(member_ids)
        ).update({EmployeeTasteProfile.cluster_id: cluster.id}, synchronize_session=False)
        created += 1

    db.commit()
    return created

"""PRD 6.1: 사번별 취향 벡터(employee_taste_profile)를 food_vector 가중평균으로 계산한다.

메뉴 데이터가 충분히 쌓이기 전까지는 이 벡터의 설명력이 제한적이므로, 6.1에서
말한 "메인메뉴 음식벡터 x 개인 선호 벡터 결합"의 1차 구현으로 본다. 이후
클러스터링/추천 고도화는 이 벡터를 입력으로 확장하면 된다.
"""

import datetime as dt

import numpy as np
from sqlalchemy.orm import Session

from app.models.logs import MealLog
from app.models.master import MenuMaster
from app.models.stats import EmployeeTasteProfile
from app.services.food_vector import FOOD_VECTOR_DIM


def compute_employee_taste_profiles(db: Session) -> int:
    """meal_log ⨝ menu_master(food_vector)를 사번별로 가중평균해 upsert한다."""
    rows = (
        db.query(MealLog.employee_id, MenuMaster.food_vector)
        .join(MenuMaster, MealLog.menu_id == MenuMaster.menu_id)
        .filter(MenuMaster.food_vector.isnot(None))
        .all()
    )

    by_employee: dict[str, list[list[float]]] = {}
    for employee_id, food_vector in rows:
        by_employee.setdefault(employee_id, []).append(list(food_vector))

    updated = 0
    for employee_id, vectors in by_employee.items():
        matrix = np.array(vectors, dtype=float)
        mean_vector = matrix.mean(axis=0).tolist()

        existing = db.query(EmployeeTasteProfile).filter_by(employee_id=employee_id).one_or_none()
        if existing is None:
            existing = EmployeeTasteProfile(employee_id=employee_id, profile_vector=mean_vector)
            db.add(existing)
        existing.profile_vector = mean_vector
        existing.sample_size = len(vectors)
        existing.updated_at = dt.datetime.utcnow()
        updated += 1

    db.commit()
    return updated


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    a, b = np.array(vec_a), np.array(vec_b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


__all__ = ["compute_employee_taste_profiles", "cosine_similarity", "FOOD_VECTOR_DIM"]

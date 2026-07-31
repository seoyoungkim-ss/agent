"""PRD 6.1: 메인메뉴 음식벡터 및 개인 선호 벡터의 공통 차원 정의.

food_vector(menu_master)와 profile_vector(employee_taste_profile)는 같은 차원 순서를
공유해야 코사인 유사도 등으로 비교할 수 있다. 값은 모두 0~1로 정규화한다.
실제 서비스에서는 메뉴 특성 태깅 규칙(수작업 또는 사내 LLM 보조)이 확정되면
이 목록을 조정한다 — 지금은 PRD에 예시로 나온 특성(매운맛/단백질 등)을 기반으로 한
초기 초안이다.
"""

FOOD_VECTOR_DIMENSIONS: list[str] = [
    "spicy",  # 매운맛
    "sweet",  # 단맛
    "salty",  # 짠맛
    "sour",  # 신맛
    "oily",  # 기름진 정도
    "protein",  # 단백질 함량
    "carb",  # 탄수화물 함량 (분식/면류 포함)
    "fried",  # 튀김 여부
    "soup_based",  # 국물 여부
    "vegetable_ratio",  # 채소 비중
]

FOOD_VECTOR_DIM = len(FOOD_VECTOR_DIMENSIONS)

# PRD 6.1: 취향 군집 라벨링(app/services/taste_clustering.py)에서 사람이 읽을 수 있는
# 이름을 만들 때 쓰는 한글 표기.
FOOD_VECTOR_LABELS_KO: dict[str, str] = {
    "spicy": "매운맛",
    "sweet": "단맛",
    "salty": "짠맛",
    "sour": "신맛",
    "oily": "기름진맛",
    "protein": "단백질",
    "carb": "탄수화물",
    "fried": "튀김",
    "soup_based": "국물",
    "vegetable_ratio": "채소",
}

# PRD 8 / 6.3.3: VOE(주관식 의견) 임베딩 차원. 사내 LLM 임베딩 모델의 출력 차원에
# 맞춰야 하므로, 실제 모델이 정해지면 이 값과 관련 마이그레이션을 갱신해야 한다.
COMMENT_EMBEDDING_DIM = 768

# 캠퍼스 평균 음식벡터가 중립값(0.5)보다 이만큼 이상 높은 차원만 "편향"으로 본다
# (taste_clustering.py의 군집 라벨 임계값과 동일한 기준 재사용).
_AVERAGE_BIAS_NEUTRAL = 0.5
_AVERAGE_BIAS_DEVIATION_THRESHOLD = 0.12
_AVERAGE_BIAS_MAX_DIMENSIONS = 2


def compute_average_food_vector(vectors: list[list[float]]) -> list[float]:
    """순수 함수 — 메인메뉴 food_vector들의 축별 산술평균. 벡터가 없으면 전부 0."""
    if not vectors:
        return [0.0] * FOOD_VECTOR_DIM
    dim = len(vectors[0])
    sums = [0.0] * dim
    for vector in vectors:
        for i, value in enumerate(vector):
            sums[i] += value
    return [s / len(vectors) for s in sums]


def describe_average_bias(
    average: list[float],
    *,
    dimensions: list[str] = FOOD_VECTOR_DIMENSIONS,
    labels_ko: dict[str, str] = FOOD_VECTOR_LABELS_KO,
    neutral: float = _AVERAGE_BIAS_NEUTRAL,
    threshold: float = _AVERAGE_BIAS_DEVIATION_THRESHOLD,
    max_dimensions: int = _AVERAGE_BIAS_MAX_DIMENSIONS,
) -> str:
    """순수 함수 — 평균 벡터가 중립값보다 뚜렷이 높은 차원 1~2개를 뽑아 한 줄
    설명을 만든다(taste_clustering.py::generate_cluster_label과 같은 "평균 대비
    튀는 차원 추출" 방식). 튀는 차원이 없으면 편향이 없다는 문장을 돌려준다.
    """
    deviations = [(dimensions[i], average[i] - neutral) for i in range(len(dimensions))]
    standout = sorted(
        (d for d in deviations if d[1] >= threshold), key=lambda d: d[1], reverse=True
    )[:max_dimensions]
    if not standout:
        return "특별히 치우친 편향 없이 고르게 분포되어 있습니다."
    names = [labels_ko.get(dim, dim) for dim, _ in standout]
    return f"{'·'.join(names)} 쪽으로 치우쳐 있습니다."

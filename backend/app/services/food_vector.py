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

# PRD 8 / 6.3.3: VOE(주관식 의견) 임베딩 차원. 사내 LLM 임베딩 모델의 출력 차원에
# 맞춰야 하므로, 실제 모델이 정해지면 이 값과 관련 마이그레이션을 갱신해야 한다.
COMMENT_EMBEDDING_DIM = 768

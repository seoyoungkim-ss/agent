"""PRD 5.2/5.3: VOE(주관식 의견)를 맛/간/위생/서비스라는 고정 분류로 태깅한다.

`food_vector_tagging.py`의 키워드 규칙 패턴(짧은 문자열 → 부분일치)을 차용하되,
VOE 코멘트는 메뉴명과 달리 여러 주제를 동시에 언급하는 자유 문장이라 **다중
라벨**로 설계한다(예: "맛도 없고 위생도 별로예요" → 맛+위생 둘 다). K-means +
사내 LLM 기반의 `voe_clustering.py`(매달 라벨이 바뀌는 자유형 클러스터)와 달리,
이 분류는 고정된 4개 카테고리라 리더가 매달 같은 틀로 훑어볼 수 있다.

키워드셋은 초기 초안이다(food_vector_tagging.py와 동일한 컨벤션) — 실제 코멘트
데이터를 보면서 계속 보강해야 한다.
"""

VOE_CATEGORIES: list[str] = ["맛", "간", "위생", "서비스"]
OTHER_CATEGORY = "기타"

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "맛": ("맛있", "맛없", "맛나", "노맛", "존맛", "밍밍", "느끼"),
    "간": ("짜요", "짜네", "짜서", "너무짜", "싱거워", "싱겁", "간이"),
    "위생": ("위생", "청결", "머리카락", "이물질", "벌레", "곰팡이", "상했", "냄새나"),
    "서비스": ("불친절", "친절", "서비스", "응대", "대기시간", "줄이길", "직원"),
}


def classify_voe_categories(comment: str) -> list[str]:
    """댓글 하나가 여러 분류에 동시에 매칭될 수 있다(다중 라벨).

    하나도 안 걸리면 빈 리스트를 반환한다 — 호출부가 이 경우 "기타"로 집계한다.
    """
    return [
        category
        for category in VOE_CATEGORIES
        if any(kw in comment for kw in _CATEGORY_KEYWORDS[category])
    ]

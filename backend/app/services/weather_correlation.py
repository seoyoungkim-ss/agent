"""§81: 메뉴별 일별 식수와 기온/강수량의 상관관계 — "기온이 오를수록/비가
올수록 식수가 느는(또는 주는) 메뉴가 있는지" 담당자 질문에 답하기 위한
순수 함수. 기존 날씨유형(§71)·계절(§72) 랭킹은 임계값을 넘는 날만 범주로
묶어 비교하는 방식이라, 이건 그와 달리 연속값 상관계수를 낸다.

holidays.py/weather_event.py의 관례와 동일하게 DB 접근 없는 순수 함수로
만들어 빠르게 단위 테스트한다.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def pearson_correlation(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """xs/ys는 같은 길이여야 하며 (기온 또는 강수량, 식수) 페어라고 가정한다.

    표본이 2개 미만이거나 한쪽이라도 분산이 0이면(모든 값이 같으면) 상관계수를
    정의할 수 없어 None — 호출부가 표본수 자체도 최소 기준(min_days)으로
    한 번 더 거르므로, 여기 None은 "정의 불가"만 나타낸다.
    """
    n = len(xs)
    if n != len(ys) or n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return None
    return cov / math.sqrt(var_x * var_y)

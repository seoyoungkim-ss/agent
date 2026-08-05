"""메뉴 회전 이력 — 같은 메뉴가 너무 자주 편성되는 걸 잡아낸다 (2순위, 2026-08).

담당자 요청: "메뉴 회전 이력 관리 (중복 편성 최소화)" +
"메인메뉴/부찬/건강가든 메뉴 조합 중복 최소화".

판정 기준은 두 가지를 같이 본다:

1. **절대 기준** — 직전 편성 이후 `MIN_ROTATION_GAP_DAYS`(14일, 구내식당의
   2주 사이클 통념)를 못 채우면 "재편성 과다".
2. **상대 기준** — 그 메뉴가 원래 몇 일 주기로 나왔는지(`avg_interval_days`)에
   비해 얼마나 이른지. 원래 60일 주기로 나오던 메뉴가 20일 만에 나오면
   절대 기준(14일)은 통과해도 이례적이므로 "평소보다 이름"으로 짚어준다.

절대 기준만 쓰면 원래 매주 나오는 김치·밥 같은 상시 부찬이 전부 경고로 뜨고,
상대 기준만 쓰면 이력이 1회뿐인 메뉴(평균 주기 계산 불가)를 놓친다.

이 모듈은 DB를 모른다 — 날짜 목록만 받는 순수 함수라 테스트가 쉽다.
DB 조회는 `app/api/analysis.py`의 엔드포인트가 맡는다(레포 관례).
"""

import datetime as dt
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

# 구내식당 메뉴 사이클 통념 — 2주 안에 같은 메뉴가 또 나오면 "너무 잦다"로 본다.
# 실측 근거가 아니라 운영 관행 기반 기본값이라 담당자 피드백으로 조정 가능하다.
MIN_ROTATION_GAP_DAYS = 14
# 평소 주기 대비 이 비율보다 짧게 돌아오면 "평소보다 이름"
EARLY_RATIO = 0.6
# 평소 주기 대비 이 배수를 넘으면 "오랜만" (재등장 후보로 쓰라는 신호)
LONG_ABSENT_RATIO = 2.0
# 한 주에 이 횟수를 넘게 편성된 메뉴는 조합이 단조롭다는 신호
OVERUSE_COUNT_IN_PERIOD = 3


class RotationFlag(str, Enum):
    SAME_DAY = "같은 날 중복"  # 같은 날 다른 코너/끼니에 또 나옴
    TOO_SOON = "재편성 과다"  # 직전 편성 이후 MIN_ROTATION_GAP_DAYS 미만
    EARLY = "평소보다 이름"  # 절대 기준은 통과, 그 메뉴 평균 주기 대비 이름
    NORMAL = "적정"
    LONG_ABSENT = "오랜만"  # 평균 주기의 LONG_ABSENT_RATIO 배 이상 만에 등장
    FIRST_TIME = "이력 없음"  # 이 기간 전 편성 이력이 없음(신메뉴이거나 데이터 부족)


@dataclass(frozen=True)
class RotationVerdict:
    flag: RotationFlag
    gap_days: int | None  # 직전 편성 이후 경과일 (이력 없으면 None)
    avg_interval_days: float | None  # 과거 편성 간격 평균 (2회 미만이면 None)
    previous_date: dt.date | None


def average_interval_days(dates: Sequence[dt.date]) -> float | None:
    """편성 날짜들의 평균 간격. 2회 미만이면 계산 불가라 None.

    `menu_performance.compute_menu_frequency`와 같은 계산이지만 그쪽은 식수·
    평가건수까지 묶은 취식 기준 통계라, 편성(weekly_menu_plan) 기준만 필요한
    여기서 그대로 쓰기엔 인자가 안 맞는다. 계산식은 동일하게 유지한다.
    """
    unique = sorted(set(dates))
    if len(unique) < 2:
        return None
    return statistics.fmean((unique[i + 1] - unique[i]).days for i in range(len(unique) - 1))


def classify_rotation(
    target_date: dt.date,
    past_dates: Sequence[dt.date],
    *,
    min_gap_days: int = MIN_ROTATION_GAP_DAYS,
) -> RotationVerdict:
    """target_date에 이 메뉴를 편성하는 게 적절한지 과거 편성일 기준으로 판정.

    past_dates에 target_date와 같은 날짜가 섞여 있어도 된다 — 같은 날 다른
    코너에 중복 편성된 경우를 SAME_DAY로 잡아내기 위해서다.
    """
    prior = sorted(d for d in set(past_dates) if d <= target_date)
    same_day = [d for d in past_dates if d == target_date]
    # 같은 날짜가 2번 이상 들어왔다 = 같은 날 다른 슬롯에도 편성됐다
    if len(same_day) >= 2:
        return RotationVerdict(
            flag=RotationFlag.SAME_DAY,
            gap_days=0,
            avg_interval_days=average_interval_days(prior),
            previous_date=target_date,
        )

    before = [d for d in prior if d < target_date]
    if not before:
        return RotationVerdict(
            flag=RotationFlag.FIRST_TIME, gap_days=None, avg_interval_days=None, previous_date=None
        )

    previous = before[-1]
    gap = (target_date - previous).days
    # 평균 주기는 "과거끼리의 간격"으로 낸다 — 이번 등장을 넣으면 판정하려는
    # 값이 기준에도 섞여 들어가 자기 자신을 정상으로 만드는 순환이 된다.
    avg = average_interval_days(before)

    if gap < min_gap_days:
        flag = RotationFlag.TOO_SOON
    elif avg is not None and gap < avg * EARLY_RATIO:
        flag = RotationFlag.EARLY
    elif avg is not None and gap > avg * LONG_ABSENT_RATIO:
        flag = RotationFlag.LONG_ABSENT
    else:
        flag = RotationFlag.NORMAL

    return RotationVerdict(flag=flag, gap_days=gap, avg_interval_days=avg, previous_date=previous)


@dataclass(frozen=True)
class OverusedMenu:
    menu_name: str
    menu_role: str
    count: int
    dates: list[dt.date]


def find_overused_menus(
    planned: Sequence[tuple[dt.date, str, str]],
    *,
    threshold: int = OVERUSE_COUNT_IN_PERIOD,
) -> list[OverusedMenu]:
    """조회 기간 안에서 같은 메뉴가 threshold 회를 넘게 편성된 것들.

    `planned`는 (plan_date, menu_name, menu_role) 튜플들. 메인/부찬/건강가든을
    구분하지 않고 한 번에 받는 이유는, 담당자 요청이 "메인메뉴/부찬/건강가든
    **조합**의 중복 최소화"라 역할을 가로질러 봐야 하기 때문이다 — 같은 나물이
    어떤 날은 부찬, 어떤 날은 건강가든으로 들어가도 먹는 사람에겐 중복이다.
    """
    buckets: dict[str, list[tuple[dt.date, str]]] = {}
    for plan_date, menu_name, menu_role in planned:
        buckets.setdefault(menu_name, []).append((plan_date, menu_role))

    results = []
    for menu_name, entries in buckets.items():
        if len(entries) <= threshold:
            continue
        # 역할이 섞여 있으면 가장 많이 쓰인 역할로 대표 표기한다.
        roles = [role for _, role in entries]
        dominant_role = max(set(roles), key=roles.count)
        results.append(
            OverusedMenu(
                menu_name=menu_name,
                menu_role=dominant_role,
                count=len(entries),
                dates=sorted(d for d, _ in entries),
            )
        )
    results.sort(key=lambda o: (-o.count, o.menu_name))
    return results

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
    corner_name: str = ""  # 어느 코너에서 반복됐는지 (2026-08 이후 항상 채워진다)


# 건강가든은 특정 코너 소속처럼 저장되지만 실제로는 **누구나 가져가는 공용**이다.
# 그래서 코너 안에서만 중복을 볼 때도 건강가든만은 코너를 가로질러 겹친 것으로 센다
# (담당자: "중복은 코너 안에서 봐야함 ... 건강가든하고만 중복 봐야함").
HEALTH_GARDEN_ROLE = "건강가든"


def build_corner_menu_dates(
    planned: Sequence[tuple[dt.date, str, str, str]],
) -> dict[tuple[str, str], list[dt.date]]:
    """`(코너, 메뉴) -> 등장 날짜 목록`. 건강가든 등장일은 **모든 코너에 합친다.**

    `planned`는 `(plan_date, corner_name, menu_name, menu_role)` 튜플들.

    담당자 요청(2026-08): "포기김치가 다른 코너에서 각각 나왔다고 중복이면 안 되고".
    예전엔 코너를 아예 안 봐서 한식 포기김치와 분식 포기김치가 같은 메뉴의 반복
    편성으로 잡혔다. 이제 코너 안에서 보되, 건강가든은 공용이므로 어느 코너
    부찬과 겹쳐도 중복으로 본다.

    ⚠️ **같은 날짜 중복을 일부러 남긴다.** `classify_rotation`이 SAME_DAY를 리스트
    안의 날짜 중복으로 판정하기 때문이다. 이 구조 덕에 "한식 부찬 나물 + 같은 날
    건강가든 나물"은 SAME_DAY로 잡히고, "한식 김치 + 분식 김치"는 각 코너에 한
    번씩만 들어가 안 잡힌다 — 정확히 담당자가 요청한 구분이다.
    횟수를 셀 때는 부르는 쪽에서 `set()`으로 접는다(`find_overused_menus`).
    """
    corners = {corner for _, corner, _, _ in planned}
    by_key: dict[tuple[str, str], list[dt.date]] = {}
    health_garden_dates: dict[str, list[dt.date]] = {}

    for plan_date, corner_name, menu_name, menu_role in planned:
        if menu_role == HEALTH_GARDEN_ROLE:
            health_garden_dates.setdefault(menu_name, []).append(plan_date)
        else:
            by_key.setdefault((corner_name, menu_name), []).append(plan_date)

    # 건강가든 등장일을 모든 코너에 얹는다 — 그 코너에 같은 날 같은 메뉴가 이미
    # 있으면 날짜가 두 번 들어가 SAME_DAY로 잡힌다(의도).
    for menu_name, dates in health_garden_dates.items():
        for corner_name in corners:
            by_key.setdefault((corner_name, menu_name), []).extend(dates)

    for dates in by_key.values():
        dates.sort()
    return by_key


def find_overused_menus(
    planned: Sequence[tuple[dt.date, str, str, str]],
    *,
    threshold: int = OVERUSE_COUNT_IN_PERIOD,
) -> list[OverusedMenu]:
    """조회 기간 안에서 **같은 코너에** 같은 메뉴가 threshold 회를 넘게 편성된 것들.

    `planned`는 `(plan_date, corner_name, menu_name, menu_role)` 튜플들.

    역할(메인/부찬/건강가든)을 가로질러 보는 건 유지한다 — 원 요청이 "메인메뉴/
    부찬/건강가든 **조합**의 중복 최소화"였다. 같은 나물이 어떤 날은 부찬, 어떤
    날은 건강가든으로 들어가도 먹는 사람에겐 중복이다.

    ⚠️ **코너를 가로질러서는 세지 않는다**(2026-08 담당자 기준): "포기김치가 다른
    코너에서 각각 나왔다고 중복이면 안 된다." 단 건강가든은 공용이라 예외다 —
    자세한 건 `build_corner_menu_dates` 참고.

    ⚠️ **횟수는 행이 아니라 고유 날짜로 센다.** 예전엔 행을 세서 같은 날 두 코너에
    깔린 메뉴가 2회로 잡혔다("같은날 메뉴가 두번씩 카운트됨" 신고). `count_in_window`는
    처음부터 날짜 집합으로 세고 있었으니 같은 모듈 안에서 규칙이 반대였던 셈이다.
    """
    dates_by_key = build_corner_menu_dates(planned)

    # 대표 역할 표기용 — 그 (코너, 메뉴)에서 가장 많이 쓰인 역할.
    roles_by_key: dict[tuple[str, str], list[str]] = {}
    for _, corner_name, menu_name, menu_role in planned:
        roles_by_key.setdefault((corner_name, menu_name), []).append(menu_role)

    results = []
    for (corner_name, menu_name), date_list in dates_by_key.items():
        dates = set(date_list)  # 횟수는 고유 날짜 기준(§55.2)
        if len(dates) <= threshold:
            continue
        roles = roles_by_key.get((corner_name, menu_name)) or [HEALTH_GARDEN_ROLE]
        results.append(
            OverusedMenu(
                menu_name=menu_name,
                menu_role=max(set(roles), key=roles.count),
                count=len(dates),
                dates=sorted(dates),
                corner_name=corner_name,
            )
        )
    results.sort(key=lambda o: (-o.count, o.corner_name, o.menu_name))
    return results


# ---------------------------------------------------------------------------
# 편성 빈도 — 횟수 기준 (2026-08 담당자 기준 반영)
# ---------------------------------------------------------------------------
# 담당자 기준: **"3개월에 2회까지는 무난한 편성"**. 위쪽 `MIN_ROTATION_GAP_DAYS`는
# *간격*(직전 등장 이후 며칠) 기준이라 성격이 다르다 — "14일은 넘겼지만 분기에
# 5번 나온다"는 간격 기준으로는 안 잡힌다. 그래서 *횟수* 기준을 따로 둔다.
#
# 메인과 부찬의 기준이 다른 이유: 김치·나물 같은 부찬은 자주 돌려쓰는 게 정상이고,
# 담당자도 "메인메뉴 과다 편성이 1순위 문제, 부찬도 자주 돌려쓰면 문제"라고 했다.
ROTATION_WINDOW_DAYS = 90  # 3개월
MAIN_MAX_IN_WINDOW = 2  # 메인은 3개월에 2회까지 무난 → 3회부터 과다
SIDE_MAX_IN_WINDOW = 6  # 부찬은 3개월에 6회까지 무난(약 2주에 1회)


def count_in_window(
    target_date: dt.date,
    dates: Sequence[dt.date],
    *,
    window_days: int = ROTATION_WINDOW_DAYS,
) -> int:
    """target_date를 포함해 직전 window_days 안에 몇 번 편성됐는지.

    같은 날 여러 코너에 편성된 건 1회로 센다 — "얼마나 자주 내보내나"가 질문이라
    한 날에 두 코너에 깔린 건 하루치 노출이다(그 중복은 SAME_DAY가 따로 본다).
    """
    window_start = target_date - dt.timedelta(days=window_days - 1)
    return len({d for d in dates if window_start <= d <= target_date})


def max_in_window_for_role(menu_role: str) -> int:
    """역할별 허용 횟수 — 메인이 가장 빡빡하다."""
    return MAIN_MAX_IN_WINDOW if menu_role == "메인" else SIDE_MAX_IN_WINDOW


def is_over_frequency(
    target_date: dt.date,
    dates: Sequence[dt.date],
    menu_role: str,
    *,
    window_days: int = ROTATION_WINDOW_DAYS,
) -> bool:
    """3개월 창에서 역할별 허용 횟수를 넘겼는가."""
    return count_in_window(target_date, dates, window_days=window_days) > max_in_window_for_role(
        menu_role
    )


# ---------------------------------------------------------------------------
# §86: 편성 빈도 × 성과 재설계 — "편성 주기 자체가 짧은 메뉴" / "나올 때가
# 됐는데 안 나온 메뉴". 둘 다 메뉴 단위(그 메뉴 자체의 평균 주기) 판정이라,
# `classify_rotation`의 인스턴스 단위 `gap_days`(이번 재편성이 얼마나
# 일렀나)와는 다른 질문이다. 특히 "나올 때가 됐는데 안 나온 메뉴"는
# `classify_rotation`처럼 조회 기간 안에 재편성된 행만 훑어서는 구조적으로
# 잡을 수 없다 — 그 기간에 아예 재편성이 안 된 메뉴가 대상이기 때문이다.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShortCycleMenu:
    corner_name: str
    menu_name: str
    avg_interval_days: float
    occurrence_count: int
    last_date: dt.date


def rank_by_shortest_cycle(
    dates_by_corner_menu: dict[tuple[str, str], list[dt.date]], *, min_occurrences: int = 2
) -> list[ShortCycleMenu]:
    """그 메뉴 자체의 평균 편성 주기가 짧은 순으로 랭킹한다.

    이력이 `min_occurrences`회 미만(평균 주기를 낼 수 없음)인 메뉴는 제외한다.
    """
    results = []
    for (corner_name, menu_name), dates in dates_by_corner_menu.items():
        unique = sorted(set(dates))
        if len(unique) < min_occurrences:
            continue
        avg = average_interval_days(unique)
        if avg is None:
            continue
        results.append(
            ShortCycleMenu(
                corner_name=corner_name,
                menu_name=menu_name,
                avg_interval_days=avg,
                occurrence_count=len(unique),
                last_date=unique[-1],
            )
        )
    results.sort(key=lambda r: (r.avg_interval_days, r.corner_name, r.menu_name))
    return results


@dataclass(frozen=True)
class OverdueMenu:
    corner_name: str
    menu_name: str
    avg_interval_days: float
    last_date: dt.date
    days_since_last: int


def find_overdue_menus(
    dates_by_corner_menu: dict[tuple[str, str], list[dt.date]],
    as_of: dt.date,
    *,
    min_occurrences: int = 2,
    ratio: float = LONG_ABSENT_RATIO,
) -> list[OverdueMenu]:
    """평균 주기 대비 `ratio`배 이상 안 나온 메뉴 — `classify_rotation`의
    LONG_ABSENT와 같은 임계값 개념이지만, 그건 "다시 편성된" 행에만 적용되고
    이건 조회 시점(as_of)까지 아예 재편성이 안 된 메뉴까지 포함한다.
    """
    results = []
    for (corner_name, menu_name), dates in dates_by_corner_menu.items():
        unique = sorted(set(dates))
        if len(unique) < min_occurrences:
            continue
        avg = average_interval_days(unique)
        if avg is None or avg <= 0:
            continue
        last_date = unique[-1]
        days_since_last = (as_of - last_date).days
        if days_since_last <= 0 or days_since_last <= avg * ratio:
            continue
        results.append(
            OverdueMenu(
                corner_name=corner_name,
                menu_name=menu_name,
                avg_interval_days=avg,
                last_date=last_date,
                days_since_last=days_since_last,
            )
        )
    results.sort(key=lambda r: (-(r.days_since_last / r.avg_interval_days), r.corner_name, r.menu_name))
    return results

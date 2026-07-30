"""PRD 6.2: 코너의 특정 메뉴가 나온 날에 피크타임 서브 속도가 유독 느린지 비교.

`aggregation.py::aggregate_daily_stats`는 코너/식사구분 단위로만 피크타임
처리량(분당 서브 건수)을 계산해 `daily_corner_stats`에 저장한다 — 메뉴 단위
분해가 없다. `meal_log`에는 이미 `menu_id`가 있으므로(별도 업로드가 필요한
`weekly_menu_plan`에 기대지 않는다 — 32절에서 확정한 "meal_log를 신뢰" 원칙과
동일), 이 모듈은 날짜별로 그 코너의 "대표 메뉴"(그날 `meal_log`에서 가장 많이
찍힌 `menu_id`)를 구하고, 대표 메뉴별로 평균 피크타임 처리량을 비교한다.
"""

import datetime as dt
import statistics
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.logs import MealLog


def _parse_time(value: str) -> dt.time:
    return dt.datetime.strptime(value, "%H:%M:%S").time()


def window_minutes(start: str, end: str) -> float:
    """순수 함수 — 'HH:MM:SS' 두 문자열 사이의 분(minute) 길이."""
    start_t, end_t = _parse_time(start), _parse_time(end)
    return max((dt.datetime.combine(dt.date.min, end_t) - dt.datetime.combine(dt.date.min, start_t)).total_seconds() / 60, 1)


@dataclass(frozen=True)
class DayThroughput:
    date: dt.date
    menu_id: int | None  # 그날 그 코너의 대표 메뉴(최빈 menu_id) — 메뉴 연결이 안 됐으면 None
    throughput: float


@dataclass(frozen=True)
class MenuThroughputEntry:
    menu_id: int
    avg_throughput: float
    day_count: int


@dataclass(frozen=True)
class MenuThroughputSummary:
    overall_avg_throughput: float | None
    menus: list[MenuThroughputEntry]  # avg_throughput 오름차순(느린 메뉴 먼저)


def build_corner_daily_throughput(
    db: Session,
    corner_id: int,
    period_start: dt.date,
    period_end: dt.date,
    settings: Settings | None = None,
) -> list[DayThroughput]:
    """기간 내 그 코너의 날짜별 (대표 메뉴, 피크타임 분당 서브)를 만든다."""
    settings = settings or get_settings()
    period_start_dt = dt.datetime.combine(period_start, dt.time())
    period_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())

    rows = (
        db.query(MealLog)
        .filter(
            MealLog.corner_id == corner_id,
            MealLog.eaten_at >= period_start_dt,
            MealLog.eaten_at < period_end_exclusive,
        )
        .all()
    )

    by_date: dict[dt.date, list[MealLog]] = {}
    for row in rows:
        by_date.setdefault(row.eaten_at.date(), []).append(row)

    results = []
    for date, day_rows in by_date.items():
        peak_start = dt.datetime.combine(date, _parse_time(settings.peak_time_start))
        peak_end = dt.datetime.combine(date, _parse_time(settings.peak_time_end))
        peak_minutes = window_minutes(settings.peak_time_start, settings.peak_time_end)
        peak_count = sum(1 for r in day_rows if peak_start <= r.eaten_at < peak_end)
        throughput = peak_count / peak_minutes

        menu_ids = [r.menu_id for r in day_rows if r.menu_id is not None]
        dominant_menu_id = Counter(menu_ids).most_common(1)[0][0] if menu_ids else None

        results.append(DayThroughput(date=date, menu_id=dominant_menu_id, throughput=throughput))

    return results


def compute_menu_throughput_summary(
    days: list[DayThroughput], *, min_day_count: int = 2
) -> MenuThroughputSummary:
    """순수 함수 — 대표 메뉴별 평균 처리량과 전체 평균(baseline)을 계산한다.

    `menu_id`가 `None`인 날(그 코너 취식 기록은 있지만 메뉴 연결이 안 된 경우)은
    메뉴별 집계에서는 빠지지만 전체 평균(baseline)에는 포함한다. 등장 일수가
    `min_day_count` 미만인 메뉴는 표본 부족으로 제외한다(4분면의 `low_sample`
    처리와 같은 사상).
    """
    all_throughputs = [d.throughput for d in days]
    overall_avg = statistics.fmean(all_throughputs) if all_throughputs else None

    by_menu: dict[int, list[float]] = {}
    for d in days:
        if d.menu_id is not None:
            by_menu.setdefault(d.menu_id, []).append(d.throughput)

    entries = [
        MenuThroughputEntry(menu_id=menu_id, avg_throughput=statistics.fmean(values), day_count=len(values))
        for menu_id, values in by_menu.items()
        if len(values) >= min_day_count
    ]
    entries.sort(key=lambda e: e.avg_throughput)

    return MenuThroughputSummary(overall_avg_throughput=overall_avg, menus=entries)


def build_corner_daily_peak_share(
    db: Session,
    corner_id: int,
    period_start: dt.date,
    period_end: dt.date,
    settings: Settings | None = None,
) -> tuple[int, int]:
    """그 코너의 기간 내 (피크타임 건수, 전체 중식시간대 건수) 합계.

    "혼잡 예상" 계산이 예전엔 예상 식수 전체를 피크타임 처리량 하나로 나눠
    비현실적으로 큰 숫자가 나왔다(2026-07 실사용 피드백) — 전체 중식시간대
    (settings.meal_period_start~end) 대비 피크타임에 실제로 얼마나 몰리는지
    실측 비율을 구해서 보정하기 위한 원자료. `build_corner_daily_throughput`과
    같은 방식(전체 행을 가져와 파이썬에서 시각 비교)으로 DB 방언에 무관하게 만든다.
    """
    settings = settings or get_settings()
    period_start_dt = dt.datetime.combine(period_start, dt.time())
    period_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())

    rows = (
        db.query(MealLog.eaten_at)
        .filter(
            MealLog.corner_id == corner_id,
            MealLog.eaten_at >= period_start_dt,
            MealLog.eaten_at < period_end_exclusive,
        )
        .all()
    )

    peak_start_t = _parse_time(settings.peak_time_start)
    peak_end_t = _parse_time(settings.peak_time_end)
    meal_start_t = _parse_time(settings.meal_period_start)
    meal_end_t = _parse_time(settings.meal_period_end)

    peak_count = 0
    meal_count = 0
    for (eaten_at,) in rows:
        t = eaten_at.time()
        if meal_start_t <= t < meal_end_t:
            meal_count += 1
            if peak_start_t <= t < peak_end_t:
                peak_count += 1

    return peak_count, meal_count


def compute_peak_share_ratio(peak_count: int, meal_count: int) -> float | None:
    """순수 함수 — 전체 중식시간대 대비 피크타임 비중(실측). 데이터 없으면 None."""
    return peak_count / meal_count if meal_count > 0 else None

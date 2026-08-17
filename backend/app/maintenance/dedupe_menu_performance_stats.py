"""menu_performance_stats에 메뉴당 쌓인 중복 스냅샷을 정리한다.

**왜 생겼나** (2026-08 "VoE 상세 클릭하면 기간이 이상하게 나옴" 신고):
`aggregate_menu_performance`(나이트 배치, 매일 새벽 2시)가 "어제 기준 최근
180일" 롤링 윈도우로 매일 새로 계산하면서, 예전엔 `(period_start,
period_end, menu_id)`가 정확히 일치하는 행만 "기존 행"으로 갱신했다. 이
윈도우는 매일 1일씩 밀리므로 그 조합이 다시는 정확히 일치하지 않고, 매일
밤 메뉴당 새 행이 하나씩 계속 쌓였다.

**앞으로는 안 생긴다** — `aggregate_menu_performance`가 이제 menu_id만으로
기존 행을 찾아 갱신한다(§104). 이 스크립트는 **이미 쌓인 것**을 치우는
용도다. 메뉴당 `period_end`가 가장 최신인 행만 남기고 나머지를 지운다.

사용법 (backend/ 디렉토리에서):
    python -m app.maintenance.dedupe_menu_performance_stats            # dry-run (기본)
    python -m app.maintenance.dedupe_menu_performance_stats --apply    # 실제 삭제

여러 번 실행해도 안전하다(idempotent) — 중복이 없으면 조용히 종료한다.
"""

import argparse
from collections import defaultdict

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.master import MenuMaster
from app.models.stats import MenuPerformanceStats


def find_duplicates(
    db: Session,
) -> list[tuple[int, MenuPerformanceStats, list[MenuPerformanceStats]]]:
    """(menu_id, 남길 행, 지울 행들) 목록. DB를 바꾸지 않는다."""
    groups: dict[int, list[MenuPerformanceStats]] = defaultdict(list)
    for row in db.query(MenuPerformanceStats).all():
        groups[row.menu_id].append(row)

    duplicates = []
    for menu_id, group in groups.items():
        if len(group) <= 1:
            continue
        group.sort(key=lambda r: (r.period_end, r.id), reverse=True)
        keeper, *rest = group
        duplicates.append((menu_id, keeper, rest))
    duplicates.sort(key=lambda item: item[0])
    return duplicates


def dedupe_menu_performance_stats(db: Session, *, apply: bool) -> int:
    duplicates = find_duplicates(db)
    if not duplicates:
        print("menu_performance_stats에 메뉴당 중복 스냅샷이 없습니다.")
        return 0

    menu_names = dict(db.query(MenuMaster.menu_id, MenuMaster.menu_name).all())

    removed = 0
    print(f"중복 메뉴 {len(duplicates)}개:\n")
    for menu_id, keeper, rest in duplicates:
        menu_name = menu_names.get(menu_id, f"menu_id={menu_id}")
        print(
            f"  {menu_name}: {len(rest) + 1}행 → 1행 "
            f"(남길 행: {keeper.period_start} ~ {keeper.period_end})"
        )
        for dup in rest:
            if apply:
                db.delete(dup)
            removed += 1

    if apply:
        db.commit()
    return removed


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="실제로 삭제한다 (없으면 dry-run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        removed = dedupe_menu_performance_stats(db, apply=args.apply)
        if removed == 0:
            return
        if not args.apply:
            print(f"\n[dry-run] {removed}행이 삭제 대상입니다. 아무것도 바꾸지 않았습니다.")
            print("실제로 지우려면 --apply를 붙이세요.")
            return
        print(f"\n✅ menu_performance_stats 중복 {removed}행을 정리했습니다.")
    finally:
        db.close()


if __name__ == "__main__":
    run()

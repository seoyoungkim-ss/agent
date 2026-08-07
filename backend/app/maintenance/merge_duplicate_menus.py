"""표기만 다른 같은 메뉴가 여러 `menu_master` 행으로 갈라진 것을 하나로 합친다.

**왜 생겼나** (2026-08 신고 "연어파피요트 취식현황에도 있고 주간식단표에 있는데
매칭이 안되고있음"): 메뉴 join이 사실상 정확 문자열 비교였다. `menu_name`이 바이트
단위 unique라 아래가 전부 별개 행이 됐다.

    연어파피요트 / 연어 파피요트 / 연어파피요트（연어:노르웨이산） / (포장)연어파피요트

식단표는 한쪽 행을, 취식기록은 다른 행을 가리키니 서로 안 붙는다. 매칭 진단은
`menu_id` 정수 비교라 **눈에 똑같은 이름이 `plan_only`와 `log_only`에 동시에** 떴다.

**앞으로는 안 생긴다** — `get_or_create_menu`가 이름이 아니라 `match_key`로 찾는다.
이 스크립트는 **이미 갈라진 것**을 합친다.

**⚠️ 삭제가 아니라 재지정(remap)이다.** `purge_origin_annotation_menus`가
`meal_log.menu_id`를 NULL로 만들어 과거 취식 이력이 영영 끊긴 전례가 있다. 여기서는
참조를 대표 행으로 옮긴 뒤에만 빈 행을 지운다.

사용법 (backend/ 디렉토리에서):
    python -m app.maintenance.merge_duplicate_menus            # dry-run (기본)
    python -m app.maintenance.merge_duplicate_menus --apply    # 실제 병합

여러 번 실행해도 안전하다(idempotent).
"""

import argparse
from collections import defaultdict

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.logs import MealLog, WeeklyMenuPlan
from app.models.master import MenuMaster
from app.services.menu_name import match_key


def _keeper_sort_key(menu: MenuMaster) -> tuple:
    """남길 행 우선순위.

    1. 사람이 손댄 값이 있는 행(food_vector_source / 신메뉴 오버라이드)을 먼저
    2. 그다음 가장 먼저 만들어진 행(작은 menu_id) — 참조가 가장 많을 가능성이 높다
    """
    has_manual = menu.food_vector_source is not None or menu.new_menu_override is not None
    return (0 if has_manual else 1, menu.menu_id)


def find_duplicate_groups(db: Session) -> list[tuple[str, MenuMaster, list[MenuMaster]]]:
    """(match_key, 남길 행, 합칠 행들). DB를 바꾸지 않는다."""
    groups: dict[str, list[MenuMaster]] = defaultdict(list)
    for menu in db.query(MenuMaster).all():
        groups[menu.match_key or match_key(menu.menu_name)].append(menu)

    duplicates = []
    for key, rows in groups.items():
        if len(rows) <= 1:
            continue
        rows.sort(key=_keeper_sort_key)
        keeper, *rest = rows
        duplicates.append((key, keeper, rest))
    duplicates.sort(key=lambda item: item[0])
    return duplicates


def merge_duplicate_menus(db: Session, *, apply: bool) -> int:
    duplicates = find_duplicate_groups(db)
    if not duplicates:
        print("표기만 다른 중복 메뉴가 없습니다.")
        return 0

    merged = 0
    print(f"중복 그룹 {len(duplicates)}개:\n")
    for _key, keeper, rest in duplicates:
        dup_ids = [m.menu_id for m in rest]
        plan_refs = (
            db.query(WeeklyMenuPlan).filter(WeeklyMenuPlan.menu_id.in_(dup_ids)).count()
        )
        log_refs = db.query(MealLog).filter(MealLog.menu_id.in_(dup_ids)).count()
        names = ", ".join(f"{m.menu_name!r}(id={m.menu_id})" for m in rest)
        print(f"  {keeper.menu_name!r}(id={keeper.menu_id}) ← {names}")
        print(f"      옮길 참조: 식단표 {plan_refs}행 / 취식기록 {log_refs}행")

        if apply:
            db.query(WeeklyMenuPlan).filter(WeeklyMenuPlan.menu_id.in_(dup_ids)).update(
                {WeeklyMenuPlan.menu_id: keeper.menu_id}, synchronize_session=False
            )
            db.query(MealLog).filter(MealLog.menu_id.in_(dup_ids)).update(
                {MealLog.menu_id: keeper.menu_id}, synchronize_session=False
            )
            # menu_snapshot_id는 weekly_menu_plan.id를 가리키므로 건드리지 않는다.
            for dup in rest:
                db.delete(dup)
        merged += len(rest)

    if apply:
        db.commit()
    return merged


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="실제로 병합한다 (없으면 dry-run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        merged = merge_duplicate_menus(db, apply=args.apply)
        if merged == 0:
            return
        if not args.apply:
            print(f"\n[dry-run] {merged}개 행이 병합 대상입니다. 아무것도 바꾸지 않았습니다.")
            print("위 목록에 **정말 같은 메뉴가 아닌 것**이 섞여 있지 않은지 먼저 확인하세요.")
            print("확인했으면 --apply를 붙이세요.")
            return
        print(f"\n✅ 중복 메뉴 {merged}개를 병합했습니다.")
        print("⚠️ 메뉴 단위 집계를 다시 계산하세요 — menu-performance/recompute와")
        print("   '최근 180일 배치 집계 재계산' 버튼.")
    finally:
        db.close()


if __name__ == "__main__":
    run()

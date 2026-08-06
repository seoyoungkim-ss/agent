"""weekly_menu_plan에 같은 메뉴가 한 슬롯에 여러 번 들어간 것을 하나로 합친다.

**왜 생겼나** (2026-08 실사용 신고 "부찬이 두번씩 들어갔고"): 재적재
(`replace_existing`)가 관리자 수동 수정 행(role_source=MANUAL)을 지우지 않는 건
맞는데, **payload는 통째로 다시 넣어서** 관리자가 손댄 메뉴가 슬롯에 두 벌씩
생겼다. `set_main_menu`가 메인을 하나 지정할 때 같은 슬롯의 다른 MAIN들을 SIDE로
내리며 전부 MANUAL로 찍으므로(weekly_menu_review.py:151-153), 메인 하나만 고쳐도
부찬 여러 개가 이 경로를 탔다.

**앞으로는 안 생긴다** — `api/ingest.py`가 MANUAL이 살아있는 메뉴는 다시 넣지
않고, 유니크 인덱스(`uq_weekly_menu_plan_slot_menu_role`)도 걸렸다. 이 스크립트는
**이미 쌓인 것**을 치우는 용도다.

**대부분은 이 스크립트가 필요 없다.** 엑셀이 남아 있는 주는 고친 백엔드로
`weekly-menu-batch`를 다시 돌리는 것만으로 정리된다. 원본 파일이 없는 과거 주에만
쓴다.

사용법 (backend/ 디렉토리에서):
    python -m app.maintenance.dedupe_weekly_menu_plan            # dry-run (기본)
    python -m app.maintenance.dedupe_weekly_menu_plan --apply    # 실제 삭제

여러 번 실행해도 안전하다(idempotent) — 중복이 없으면 조용히 종료한다.
"""

import argparse
from collections import defaultdict

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.enums import MenuRoleSource
from app.models.logs import WeeklyMenuPlan
from app.models.master import MenuMaster

# 어느 행을 남길지 — 사람 손이 닿은 것부터. 관리자가 화면에서 고친 판단이
# 파서가 넣은 값보다 우선한다(중복의 원인 자체가 이 둘의 공존이었다).
_KEEP_PRIORITY = {
    MenuRoleSource.MANUAL: 0,
    MenuRoleSource.LLM: 1,
    MenuRoleSource.RULE: 2,
}


def _slot_key(plan: WeeklyMenuPlan) -> tuple:
    return (plan.plan_date, plan.corner_id, plan.meal_type, plan.menu_id, plan.menu_role)


def _sort_key(plan: WeeklyMenuPlan) -> tuple:
    return (_KEEP_PRIORITY.get(plan.role_source, 9), plan.id)


def find_duplicates(db: Session) -> list[tuple[tuple, WeeklyMenuPlan, list[WeeklyMenuPlan]]]:
    """(슬롯키, 남길 행, 지울 행들) 목록. DB를 바꾸지 않는다."""
    groups: dict[tuple, list[WeeklyMenuPlan]] = defaultdict(list)
    for plan in db.query(WeeklyMenuPlan).all():
        groups[_slot_key(plan)].append(plan)

    duplicates = []
    for key, group in groups.items():
        if len(group) <= 1:
            continue
        group.sort(key=_sort_key)
        keeper, *rest = group
        duplicates.append((key, keeper, rest))
    duplicates.sort(key=lambda item: (item[0][0], str(item[0][2]), item[0][1]))
    return duplicates


def dedupe_weekly_menu_plan(db: Session, *, apply: bool) -> int:
    duplicates = find_duplicates(db)
    if not duplicates:
        print("한 슬롯에 중복된 식단표 행이 없습니다.")
        return 0

    # WeeklyMenuPlan에는 MenuMaster 관계가 없다 — 이름은 따로 끌어온다.
    menu_names = dict(db.query(MenuMaster.menu_id, MenuMaster.menu_name).all())

    removed = 0
    print(f"중복 그룹 {len(duplicates)}개:\n")
    for (plan_date, _corner_id, meal_type, menu_id, menu_role), keeper, rest in duplicates:
        meal = meal_type.value if hasattr(meal_type, "value") else meal_type
        role = menu_role.value if hasattr(menu_role, "value") else menu_role
        src = keeper.role_source.value if hasattr(keeper.role_source, "value") else keeper.role_source
        menu_name = menu_names.get(menu_id, f"menu_id={menu_id}")
        print(f"  {plan_date} {meal} {role} {menu_name}: {len(rest) + 1}행 → 1행 (남길 행 출처: {src})")
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
        removed = dedupe_weekly_menu_plan(db, apply=args.apply)
        if removed == 0:
            return
        if not args.apply:
            print(f"\n[dry-run] {removed}행이 삭제 대상입니다. 아무것도 바꾸지 않았습니다.")
            print("실제로 지우려면 --apply를 붙이세요.")
            return
        print(f"\n✅ 중복된 식단표 {removed}행을 정리했습니다.")
        print("⚠️ 편성 횟수·중복 점검 화면은 조회 시점에 계산하므로 별도 재집계가 필요 없습니다.")
    finally:
        db.close()


if __name__ == "__main__":
    run()

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

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.logs import MealLog, WeeklyMenuPlan
from app.models.master import MenuMaster
from app.models.stats import MenuPerformanceStats
from app.services.menu_name import match_key


def _keeper_sort_key(menu: MenuMaster) -> tuple:
    """남길 행 우선순위.

    1. 사람이 손댄 값이 있는 행(food_vector_source / 신메뉴 오버라이드)을 먼저
    2. 그다음 가장 먼저 만들어진 행(작은 menu_id) — 참조가 가장 많을 가능성이 높다
    """
    has_manual = menu.food_vector_source is not None or menu.new_menu_override is not None
    return (0 if has_manual else 1, menu.menu_id)


def _referencing_columns(db: Session) -> list[tuple[str, str]]:
    """`menu_master.menu_id`를 참조하는 (테이블, 컬럼) 전부를 DB에서 읽어온다.

    손으로 목록을 관리하면 테이블이 늘 때 놓친다 — 실제로 그래서 터졌다(2026-08:
    weekly_menu_plan·meal_log만 챙기고 menu_performance_stats를 빠뜨려
    "menu_id is still referenced from table menu_performance_stats"). 삭제 직전에
    이걸로 검사해, 새 참조가 생기면 raw IntegrityError 대신 이름을 알려준다.
    """
    rows = db.execute(
        text(
            """
            SELECT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND ccu.table_name = 'menu_master'
              AND ccu.column_name = 'menu_id'
            """
        )
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _remaining_references(db: Session, menu_ids: list[int]) -> dict[str, int]:
    """아직 그 메뉴들을 가리키고 있는 곳. 비어 있어야 안전하게 삭제된다."""
    remaining = {}
    for table, column in _referencing_columns(db):
        count = db.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE {column} = ANY(:ids)"),  # noqa: S608
            {"ids": menu_ids},
        ).scalar()
        if count:
            remaining[f"{table}.{column}"] = count
    return remaining


def backfill_missing_match_keys(db: Session) -> int:
    """`match_key`가 비어 있는 행을 채운다. 채운 개수를 반환.

    이제 모델 이벤트가 항상 계산하지만(`models/master.py`), 그 이전에 만들어진
    행이 남아 있을 수 있다 — 건강가든 수기 입력이 `get_or_create_menu`를 안 쓰던
    시절의 행들. NULL이면 조회가 못 찾아 unique 위반이 나므로 먼저 메운다.
    """
    pending = db.query(MenuMaster).filter(MenuMaster.match_key.is_(None)).all()
    for menu in pending:
        menu.match_key = match_key(menu.menu_name)
    if pending:
        db.commit()
    return len(pending)


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
    filled = backfill_missing_match_keys(db)
    if filled:
        print(f"match_key가 비어 있던 {filled}행을 먼저 채웠습니다.\n")

    duplicates = find_duplicate_groups(db)
    if not duplicates:
        print("표기만 다른 중복 메뉴가 없습니다.")
        return 0

    merged = 0
    print(f"중복 그룹 {len(duplicates)}개:\n")
    for _key, keeper, rest in duplicates:
        dup_ids = [m.menu_id for m in rest]
        dup_plans = db.query(WeeklyMenuPlan).filter(WeeklyMenuPlan.menu_id.in_(dup_ids)).all()
        log_refs = db.query(MealLog).filter(MealLog.menu_id.in_(dup_ids)).count()

        # 대표 메뉴가 그 슬롯·역할에 이미 있으면 옮길 수 없다 — 옮기면 기존 행과
        # 완전히 같아져 uq_weekly_menu_plan_slot_menu_role을 위반한다(§55.4).
        # 식단표에 두 표기가 같이 올라간 게 갈라짐의 원인이라, **병합이 필요한
        # 데이터일수록 이 충돌이 흔하다**(2026-08 실사용에서 바로 터졌다).
        keeper_slots = {
            (p.plan_date, p.corner_id, p.meal_type, p.menu_role)
            for p in db.query(WeeklyMenuPlan).filter(WeeklyMenuPlan.menu_id == keeper.menu_id)
        }
        to_remap, to_absorb = [], []
        for plan in dup_plans:
            slot = (plan.plan_date, plan.corner_id, plan.meal_type, plan.menu_role)
            if slot in keeper_slots:
                to_absorb.append(plan)  # 진짜 중복 — 대표 행에 흡수
            else:
                to_remap.append(plan)
                keeper_slots.add(slot)  # 같은 그룹 안에서 또 겹치지 않게

        # 흡수되는 행을 취식기록이 참조 중이면(FK) 먼저 살아남는 행으로 옮긴다.
        # NULL로 밀면 과거 취식 이력이 끊긴다 — §56.1에서 문제 삼은 그 실수다.
        snapshot_moves = 0
        keeper_plan_by_slot = {
            (p.plan_date, p.corner_id, p.meal_type, p.menu_role): p.id
            for p in db.query(WeeklyMenuPlan).filter(WeeklyMenuPlan.menu_id == keeper.menu_id)
        }
        for plan in to_absorb:
            slot = (plan.plan_date, plan.corner_id, plan.meal_type, plan.menu_role)
            survivor_id = keeper_plan_by_slot.get(slot)
            refs = db.query(MealLog).filter(MealLog.menu_snapshot_id == plan.id).count()
            snapshot_moves += refs
            if apply and refs and survivor_id is not None:
                db.query(MealLog).filter(MealLog.menu_snapshot_id == plan.id).update(
                    {MealLog.menu_snapshot_id: survivor_id}, synchronize_session=False
                )

        # menu_performance_stats는 **파생 집계**다(배치가 다시 만든다). 옮겨봐야
        # (period_start, period_end, menu_id) 유니크에 걸리고, 설령 안 걸려도 두
        # 행의 점수는 더할 수 있는 값이 아니라 원본에서 다시 계산해야 한다.
        # 그래서 대표 것까지 통째로 지우고 재계산에 맡긴다 — 병합으로 그 메뉴의
        # 취식 집합 자체가 바뀌었으니 대표 행 통계도 어차피 낡았다.
        group_ids = [keeper.menu_id, *dup_ids]
        stats_rows = (
            db.query(MenuPerformanceStats)
            .filter(MenuPerformanceStats.menu_id.in_(group_ids))
            .count()
        )

        names = ", ".join(f"{m.menu_name!r}(id={m.menu_id})" for m in rest)
        print(f"  {keeper.menu_name!r}(id={keeper.menu_id}) ← {names}")
        print(f"      식단표: {len(to_remap)}행 옮김 / {len(to_absorb)}행은 같은 슬롯에 이미 있어 합침")
        print(f"      취식기록: {log_refs}행 옮김")
        if snapshot_moves:
            print(f"      스냅샷 참조 재지정: {snapshot_moves}행")
        if stats_rows:
            print(f"      메뉴 성과 통계: {stats_rows}행 삭제 (재계산 필요)")

        if apply:
            for plan in to_absorb:
                db.delete(plan)
            db.flush()  # 삭제를 먼저 반영해야 아래 UPDATE가 제약에 안 걸린다
            if to_remap:
                db.query(WeeklyMenuPlan).filter(
                    WeeklyMenuPlan.id.in_([p.id for p in to_remap])
                ).update({WeeklyMenuPlan.menu_id: keeper.menu_id}, synchronize_session=False)
            db.query(MealLog).filter(MealLog.menu_id.in_(dup_ids)).update(
                {MealLog.menu_id: keeper.menu_id}, synchronize_session=False
            )
            db.query(MenuPerformanceStats).filter(
                MenuPerformanceStats.menu_id.in_(group_ids)
            ).delete(synchronize_session=False)
            db.flush()

            # 남은 참조가 있으면 여기서 멈춘다 — 그냥 지우면 raw IntegrityError가
            # 나고 어느 테이블인지 스택만 보고는 모른다(실제로 그렇게 헤맸다).
            remaining = _remaining_references(db, dup_ids)
            if remaining:
                raise RuntimeError(
                    f"{keeper.menu_name!r} 병합 중단 — 아직 참조가 남아 있습니다: {remaining}. "
                    "이 스크립트가 모르는 테이블이 생겼습니다. 그 참조를 어떻게 처리할지"
                    "(대표로 옮길지, 지울지) 정해서 merge_duplicate_menus에 추가해야 합니다."
                )
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

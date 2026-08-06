"""원산지 표기가 메뉴로 잘못 저장된 행을 정리한다 (2026-08).

주간 식단표 파서가 2026-08까지 `(계육-국산)` 같은 하이픈 표기를 못 걸러
**부찬 메뉴처럼 저장**했다(콜론만 인정하는 정규식이 파서와 백엔드에 똑같이
복제돼 있었다). 파서는 고쳤지만 **적재 경로에서만 걸러지므로 이미 들어간
데이터는 안 바뀐다** — 그래서 이 스크립트가 필요하다.

사용법 (backend/ 디렉토리에서):

    python -m app.maintenance.purge_origin_annotation_menus            # dry-run
    python -m app.maintenance.purge_origin_annotation_menus --apply    # 실제 삭제

**기본은 dry-run이다.** 무엇이 지워질지 먼저 눈으로 확인하고 `--apply`를 붙인다.
여러 번 실행해도 안전하다(idempotent) — 지울 게 없으면 조용히 끝난다.

지우는 순서와 이유:
1. `weekly_menu_plan`에서 해당 메뉴를 참조하는 행 삭제 — 유령 부찬 자체
2. `meal_log.menu_id`는 **NULL로 되돌린다**(행을 지우지 않는다) — 취식 기록은
   실제로 일어난 사실이라 없애면 식수 통계가 틀어진다. 원산지 메뉴에 취식이
   붙는 건 드물지만, 붙었다면 메뉴 연결만 끊는 게 맞다.
3. 고아가 된 `menu_master` 행 삭제

정리 후에는 식단표를 다시 업로드해야 원래 부찬이 복구된다 —
`POST /ingest/weekly-menu`에 `replace_existing=true`를 쓰면 중복 없이 재적재된다.
"""

import argparse

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.logs import MealLog, WeeklyMenuPlan
from app.models.master import MenuMaster
from app.services.menu_name import is_origin_annotation_text


def find_origin_annotation_menus(db: Session) -> list[MenuMaster]:
    """이름이 통째로 원산지 표기인 메뉴 — 판정은 menu_name.py가 단일 출처다."""
    return [m for m in db.query(MenuMaster).all() if is_origin_annotation_text(m.menu_name)]


def purge(db: Session, *, apply: bool) -> dict[str, int]:
    menus = find_origin_annotation_menus(db)
    if not menus:
        return {"menus": 0, "plan_rows": 0, "meal_log_rows": 0}

    menu_ids = [m.menu_id for m in menus]
    plan_rows = (
        db.query(WeeklyMenuPlan).filter(WeeklyMenuPlan.menu_id.in_(menu_ids)).count()
    )
    meal_log_rows = db.query(MealLog).filter(MealLog.menu_id.in_(menu_ids)).count()

    print(f"원산지 표기로 판정된 메뉴 {len(menus)}건:")
    for m in menus:
        print(f"  - {m.menu_name!r} (menu_id={m.menu_id})")
    print(f"  → 삭제될 weekly_menu_plan 행: {plan_rows}")
    print(f"  → menu_id를 NULL로 되돌릴 meal_log 행: {meal_log_rows} (행 자체는 보존)")

    if not apply:
        print("\n[dry-run] 아무것도 바꾸지 않았습니다. 실제로 지우려면 --apply를 붙이세요.")
        return {"menus": len(menus), "plan_rows": plan_rows, "meal_log_rows": meal_log_rows}

    db.query(WeeklyMenuPlan).filter(WeeklyMenuPlan.menu_id.in_(menu_ids)).delete(
        synchronize_session=False
    )
    db.query(MealLog).filter(MealLog.menu_id.in_(menu_ids)).update(
        {MealLog.menu_id: None}, synchronize_session=False
    )
    db.query(MenuMaster).filter(MenuMaster.menu_id.in_(menu_ids)).delete(
        synchronize_session=False
    )
    db.commit()
    return {"menus": len(menus), "plan_rows": plan_rows, "meal_log_rows": meal_log_rows}


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="실제로 삭제한다(기본은 dry-run)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = purge(db, apply=args.apply)
        if result["menus"] == 0:
            print("정리할 원산지 표기 메뉴가 없습니다.")
            return
        if args.apply:
            print(f"\n✅ 메뉴 {result['menus']}건과 식단표 {result['plan_rows']}행을 정리했습니다.")
            print("⚠️ 다음 순서로 마무리하세요:")
            print("   1) 주간 식단표를 다시 업로드 (ingest는 replace_existing=true 사용)")
            print("   2) '최근 180일 배치 집계 재계산' + menu-performance/recompute 호출")
    finally:
        db.close()


if __name__ == "__main__":
    run()

"""`menu_master.menu_name`에 아직 안 떨어진 원산지/재료 주석을 정정한다 (2026-08).

**왜 필요한가** — `strip_origin_annotation`(§58)이 문자열 끝에서만 동작하던
버그와, 재료-짝 폴백이 스트립 쪽엔 없던 버그를 고쳤다. 하지만 그 함수는
`match_key`를 계산할 때만 불린다(`app/models/master.py`의 `before_insert`/
`before_update` 이벤트) — **표시명(`menu_name`) 자체는 insert/update 시점에만
재계산되므로, 이미 저장된 오염된 이름은 코드를 고쳐도 저절로 안 바뀐다.**

    "햄마늘종볶음(햄-계육, 돈육:국내산)"   ← 아직 이 모양 그대로 남아 있다

이 스크립트는 `menu_name`을 `strip_origin_annotation`으로 정정된 값으로
UPDATE한다. UPDATE하면 이벤트가 `match_key`를 자동으로 재계산한다.

**병합은 여기서 하지 않는다.** `menu_name`엔 unique 제약이 있어, 정정된 이름이
이미 다른 행의 이름과 완전히 같으면 그대로 UPDATE할 수 없다(예: "햄마늘종볶음"이
이미 따로 있는데 이 행도 "햄마늘종볶음"이 되려는 경우). 그런 행은 표시명은 그대로
두고 **`match_key`만** 정정된 값으로 맞춘다 — `merge_duplicate_menus.py`가
`match_key`로 중복을 찾으므로(§57), 다음 실행에서 정확히 병합 대상으로 잡힌다.
`match_key`를 손으로 계산해 넣는 방식은 새로운 게 아니다 — 이미
`merge_duplicate_menus.backfill_missing_match_keys`가 같은 방식을 쓴다.

사용법 (backend/ 디렉토리에서), 이 순서로:

    python -m app.maintenance.rename_menus_with_leftover_annotation            # dry-run
    python -m app.maintenance.rename_menus_with_leftover_annotation --apply
    python -m app.maintenance.merge_duplicate_menus            # dry-run
    python -m app.maintenance.merge_duplicate_menus --apply

여러 번 실행해도 안전하다(idempotent) — 정정할 이름이 없으면 조용히 끝난다.
"""

import argparse

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.master import MenuMaster
from app.services.menu_name import match_key, strip_origin_annotation


def find_leftover_annotation_menus(db: Session) -> list[tuple[MenuMaster, str]]:
    """(행, 정정된 이름) — 정정해도 원문과 같으면 대상이 아니다."""
    pending = []
    for menu in db.query(MenuMaster).all():
        corrected = strip_origin_annotation(menu.menu_name)
        if corrected and corrected != menu.menu_name:
            pending.append((menu, corrected))
    return pending


def rename(db: Session, *, apply: bool) -> int:
    pending = find_leftover_annotation_menus(db)
    if not pending:
        print("정정할 메뉴명이 없습니다.")
        return 0

    # menu_name은 unique라 정정된 이름이 이미 다른 행이 쓰고 있으면 그대로 못
    # 옮긴다. 이번 배치에서 먼저 옮겨진 이름도 다시 못 쓰게 여기서 같이 추적한다.
    taken_names = {m.menu_name for m in db.query(MenuMaster).all()}

    print(f"주석이 안 떨어진 메뉴 {len(pending)}건:\n")
    renamed = 0
    for menu, corrected in pending:
        collides = corrected in taken_names
        if collides:
            print(
                f"  {menu.menu_name!r}(id={menu.menu_id}) → match_key만 정정 "
                f"(표시명은 {corrected!r}와 겹쳐 그대로 둠 — merge_duplicate_menus로 이어서 처리)"
            )
        else:
            print(f"  {menu.menu_name!r}(id={menu.menu_id}) → {corrected!r}")
            taken_names.add(corrected)

        if apply:
            if collides:
                menu.match_key = match_key(corrected)
            else:
                menu.menu_name = corrected
            renamed += 1

    if apply:
        db.commit()
    else:
        print(f"\n[dry-run] {len(pending)}건이 정정 대상입니다. 아무것도 바꾸지 않았습니다.")
        print("확인했으면 --apply를 붙이세요. 그 다음 merge_duplicate_menus를 실행하세요.")

    return renamed


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="실제로 정정한다 (없으면 dry-run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        renamed = rename(db, apply=args.apply)
        if args.apply and renamed:
            print(f"\n✅ 메뉴명 {renamed}건을 정정했습니다.")
            print("⚠️ 이어서 merge_duplicate_menus를 실행해 겹치는 이름을 병합하세요.")
    finally:
        db.close()


if __name__ == "__main__":
    run()

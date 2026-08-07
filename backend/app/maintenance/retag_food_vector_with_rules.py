"""이미 규칙/LLM으로 태깅된 `food_vector`를 최신 키워드 규칙으로 다시 계산한다 (2026-08).

**왜 필요한가** — `tag_food_vector_from_name`(규칙 기반 태깅)은 신메뉴가 처음
들어올 때(`get_or_create_menu`)만 호출된다. 그 뒤 규칙표를 고쳐도(예: "탕수육"이
"탕"을 포함한다고 국물로 오태깅되던 버그 수정) **이미 저장된 `food_vector`는
저절로 안 바뀐다** — §58의 `match_key`, §57의 `menu_name`과 같은 문제다.

    "탕수육" → soup_based가 이미 0.85로 저장돼 있다 (규칙 고치기 전에 태깅됨)

이 스크립트는 `food_vector_source`가 `MANUAL`이 아닌 모든 행(RULE 또는 LLM으로
채워진 행, 그리고 어쩌다 NULL인 행)에 대해 `tag_food_vector_from_name`을 다시
호출해, 새로 계산한 벡터가 기존 값과 다르면 갱신한다. 규칙이 이번엔 매칭되면
`source`를 `RULE`로 맞춘다 — 신메뉴 최초 태깅과 같은 우선순위(규칙 → LLM)를
기존 데이터에도 그대로 적용하는 것뿐이다.

**관리자가 수동으로 조정한 행(`MANUAL`)은 절대 건드리지 않는다** — food_vector
3단계 태깅의 공통 규칙(§118 이후 계속 지켜온 관례)과 같다.

사용법 (backend/ 디렉토리에서):

    python -m app.maintenance.retag_food_vector_with_rules            # dry-run
    python -m app.maintenance.retag_food_vector_with_rules --apply    # 실제 갱신

여러 번 실행해도 안전하다(idempotent) — 규칙표가 그대로면 다시 돌려도 바뀔 게 없다.
"""

import argparse

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.enums import FoodVectorSource
from app.models.master import MenuMaster
from app.services.food_vector import FOOD_VECTOR_DIMENSIONS
from app.services.food_vector_tagging import tag_food_vector_from_name


def find_stale_food_vectors(db: Session) -> list[tuple[MenuMaster, list[float]]]:
    """(행, 새로 계산한 벡터) — 값이 그대로면 대상이 아니다."""
    stale = []
    query = db.query(MenuMaster).filter(MenuMaster.food_vector_source != FoodVectorSource.MANUAL)
    for menu in query:
        vector, matched_any = tag_food_vector_from_name(menu.menu_name)
        if not matched_any:
            continue  # 규칙이 하나도 안 걸리면 기존 값(LLM 추정 등)을 건드리지 않는다
        if menu.food_vector is None or list(menu.food_vector) != vector:
            stale.append((menu, vector))
    return stale


def _diff_summary(old: list[float] | None, new: list[float]) -> str:
    if old is None:
        return "(기존 NULL)"
    changed = [
        f"{dim}: {o:.2f}→{n:.2f}"
        for dim, o, n in zip(FOOD_VECTOR_DIMENSIONS, old, new)
        if abs(o - n) > 1e-9
    ]
    return ", ".join(changed)


def retag(db: Session, *, apply: bool) -> int:
    stale = find_stale_food_vectors(db)
    if not stale:
        print("갱신할 food_vector가 없습니다.")
        return 0

    print(f"규칙 재적용으로 값이 바뀌는 메뉴 {len(stale)}건:\n")
    for menu, vector in stale:
        print(f"  {menu.menu_name!r}(id={menu.menu_id}) — {_diff_summary(menu.food_vector, vector)}")
        if apply:
            menu.food_vector = vector
            menu.food_vector_source = FoodVectorSource.RULE

    if apply:
        db.commit()
    else:
        print(f"\n[dry-run] {len(stale)}건이 갱신 대상입니다. 아무것도 바꾸지 않았습니다.")
        print("확인했으면 --apply를 붙이세요.")

    return len(stale)


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="실제로 갱신한다 (없으면 dry-run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        updated = retag(db, apply=args.apply)
        if args.apply and updated:
            print(f"\n✅ food_vector {updated}건을 갱신했습니다.")
    finally:
        db.close()


if __name__ == "__main__":
    run()

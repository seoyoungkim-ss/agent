"""이미 저장된 메뉴명에 남은 원산지/재료 주석 정정 (2026-08).

`strip_origin_annotation`(§58) 버그를 고쳐도 **이미 저장된 `menu_master.
menu_name`은 저절로 안 바뀐다** — 그 함수는 insert/update 시점에만 불린다.
이 스크립트가 남은 오염을 정정한다.
"""

from app.maintenance.rename_menus_with_leftover_annotation import rename
from app.models.master import MenuMaster
from app.services.menu_name import match_key


def test_renames_menu_with_leftover_trailing_annotation(db_session):
    """기존 정상 케이스 — 끝에 있는 원산지 주석."""
    menu = MenuMaster(menu_name="우삼겹구이(우육:호주산, 돈육:국내산)")
    db_session.add(menu)
    db_session.commit()

    rename(db_session, apply=True)

    db_session.refresh(menu)
    assert menu.menu_name == "우삼겹구이"
    assert menu.match_key == match_key("우삼겹구이")


def test_renames_menu_with_non_trailing_annotation(db_session):
    """신고 재현 — 괄호 뒤에 "&메뉴명"이 더 있어 안 떨어지던 케이스."""
    menu = MenuMaster(menu_name="명란크림파스타(명란:미국산)&베이컨포테이토피자")
    db_session.add(menu)
    db_session.commit()

    rename(db_session, apply=True)

    db_session.refresh(menu)
    assert menu.menu_name == "명란크림파스타&베이컨포테이토피자"


def test_renames_menu_with_ingredient_pair_annotation(db_session):
    """신고 재현 — 원산지가 아닌 재료 짝("햄-계육")만 있는 케이스."""
    menu = MenuMaster(menu_name="햄마늘종볶음(햄-계육, 돈육:국내산)")
    db_session.add(menu)
    db_session.commit()

    rename(db_session, apply=True)

    db_session.refresh(menu)
    assert menu.menu_name == "햄마늘종볶음"


def test_menu_without_annotation_is_left_alone(db_session):
    menu = MenuMaster(menu_name="김치찌개")
    db_session.add(menu)
    db_session.commit()

    changed = rename(db_session, apply=True)

    assert changed == 0
    db_session.refresh(menu)
    assert menu.menu_name == "김치찌개"


def test_dry_run_changes_nothing(db_session):
    menu = MenuMaster(menu_name="햄마늘종볶음(햄-계육, 돈육:국내산)")
    db_session.add(menu)
    db_session.commit()

    rename(db_session, apply=False)

    db_session.refresh(menu)
    assert menu.menu_name == "햄마늘종볶음(햄-계육, 돈육:국내산)"


def test_is_idempotent(db_session):
    menu = MenuMaster(menu_name="햄마늘종볶음(햄-계육, 돈육:국내산)")
    db_session.add(menu)
    db_session.commit()

    rename(db_session, apply=True)
    assert rename(db_session, apply=True) == 0


def test_colliding_correction_updates_match_key_without_violating_unique_name(db_session):
    """정정된 이름이 이미 다른 행이 쓰고 있으면 표시명은 못 옮기고 match_key만 맞춘다.

    `menu_name`은 unique라 그대로 UPDATE하면 IntegrityError가 난다. 다음 단계인
    `merge_duplicate_menus`가 `match_key`로 중복을 찾으므로, 여기서는 그 값만
    정정해 다음 실행에서 병합 대상으로 잡히게 한다.
    """
    clean = MenuMaster(menu_name="햄마늘종볶음")
    dirty = MenuMaster(menu_name="햄마늘종볶음(햄-계육, 돈육:국내산)")
    db_session.add_all([clean, dirty])
    db_session.commit()

    rename(db_session, apply=True)

    db_session.refresh(clean)
    db_session.refresh(dirty)
    assert dirty.menu_name == "햄마늘종볶음(햄-계육, 돈육:국내산)", "표시명이 강제로 옮겨져 unique 위반이 났으면 안 된다"
    assert dirty.match_key == clean.match_key == match_key("햄마늘종볶음")


def test_rename_then_merge_end_to_end(db_session):
    """정정 스크립트가 만든 match_key 충돌을 merge_duplicate_menus가 이어서 처리하는지.

    plan에서 요구한 운영 순서 검증: rename_menus_with_leftover_annotation →
    merge_duplicate_menus.
    """
    from app.maintenance.merge_duplicate_menus import merge_duplicate_menus

    clean = MenuMaster(menu_name="햄마늘종볶음")
    dirty = MenuMaster(menu_name="햄마늘종볶음(햄-계육, 돈육:국내산)")
    db_session.add_all([clean, dirty])
    db_session.commit()

    rename(db_session, apply=True)
    merged = merge_duplicate_menus(db_session, apply=True)

    assert merged == 1
    remaining = db_session.query(MenuMaster).all()
    assert len(remaining) == 1
    assert remaining[0].menu_name == "햄마늘종볶음"

from app.services.master_data import TAKE_OUT_CORNER_NAME, get_or_create_corner


def test_take_out_aliases_merge_into_single_corner(db_session):
    r, r_is_new = get_or_create_corner(db_session, "Take Out R")
    m, m_is_new = get_or_create_corner(db_session, "Take Out M")
    l, l_is_new = get_or_create_corner(db_session, "Take Out L")

    assert r_is_new is True
    assert m_is_new is False
    assert l_is_new is False
    assert r.corner_id == m.corner_id == l.corner_id
    assert r.corner_name == TAKE_OUT_CORNER_NAME


def test_unrelated_corner_name_unaffected(db_session):
    corner, is_new = get_or_create_corner(db_session, "한식")
    assert is_new is True
    assert corner.corner_name == "한식"

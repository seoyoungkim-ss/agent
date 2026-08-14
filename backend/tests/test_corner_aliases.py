from app.services.corner_aliases import CORNER_DISPLAY_ORDER, corner_display_sort_key


def test_corner_display_sort_key_orders_listed_corners_by_index():
    keys = [corner_display_sort_key(idx, name) for idx, name in enumerate(CORNER_DISPLAY_ORDER)]
    assert keys == sorted(keys)
    assert keys[0][0] == 0
    assert keys[-1][0] == len(CORNER_DISPLAY_ORDER) - 1


def test_corner_display_sort_key_pushes_unlisted_corners_to_the_end():
    listed = corner_display_sort_key(999, CORNER_DISPLAY_ORDER[0])
    unlisted = corner_display_sort_key(1, "테스트코너71")
    assert listed < unlisted


def test_corner_display_sort_key_breaks_ties_among_unlisted_corners_by_corner_id():
    a = corner_display_sort_key(5, "테스트코너71")
    b = corner_display_sort_key(10, "폐지된코너")
    assert a < b


def test_corner_display_sort_key_sorts_a_mixed_corner_set_end_to_end():
    corners = [
        (11, "테스트코너71"),
        (1, CORNER_DISPLAY_ORDER[2]),
        (2, CORNER_DISPLAY_ORDER[0]),
        (3, "폐지된코너"),
        (4, CORNER_DISPLAY_ORDER[1]),
    ]
    ordered = sorted(corners, key=lambda c: corner_display_sort_key(c[0], c[1]))
    ordered_names = [name for _, name in ordered]
    assert ordered_names == [
        CORNER_DISPLAY_ORDER[0],
        CORNER_DISPLAY_ORDER[1],
        CORNER_DISPLAY_ORDER[2],
        "폐지된코너",
        "테스트코너71",
    ]

import pytest

from app.services.menu_affinity import compute_menu_affinity, compute_top_menu_pairs, is_obvious_pair


def test_strong_co_occurrence_has_high_lift():
    # 떡볶이 먹는 사람 4명 중 3명이 짜장면도 먹음 — 강한 연관
    employee_menus = {
        "E1": {"떡볶이", "짜장면"},
        "E2": {"떡볶이", "짜장면"},
        "E3": {"떡볶이", "짜장면"},
        "E4": {"떡볶이"},
        "E5": {"짜장면"},
        "E6": {"돈까스"},
        "E7": {"돈까스"},
        "E8": {"돈까스"},
    }
    results = compute_menu_affinity(employee_menus, "떡볶이", min_co_count=2)
    names = [r.menu_name for r in results]
    assert "짜장면" in names
    jjajang = next(r for r in results if r.menu_name == "짜장면")
    assert jjajang.co_count == 3
    assert jjajang.lift > 1  # 우연보다 더 자주 같이 나옴


def test_independent_menus_have_lift_near_one():
    # 모든 사람이 A와 B 둘 다 절반씩 무작위로 먹었다고 가정한 것과 유사한 분포
    employee_menus = {
        "E1": {"A", "B"},
        "E2": {"A"},
        "E3": {"B"},
        "E4": {},
        "E5": {"A", "B"},
        "E6": {"A"},
        "E7": {"B"},
        "E8": {},
    }
    results = compute_menu_affinity(employee_menus, "A", min_co_count=1)
    b = next(r for r in results if r.menu_name == "B")
    assert 0.5 < b.lift < 2.0  # 극단적으로 몰리지 않음


def test_target_menu_excluded_from_results():
    employee_menus = {"E1": {"떡볶이"}, "E2": {"떡볶이"}, "E3": {"떡볶이"}}
    results = compute_menu_affinity(employee_menus, "떡볶이", min_co_count=1)
    assert all(r.menu_name != "떡볶이" for r in results)


def test_min_co_count_filters_noise():
    employee_menus = {
        "E1": {"떡볶이", "특이메뉴"},
        "E2": {"떡볶이"},
        "E3": {"떡볶이"},
    }
    results = compute_menu_affinity(employee_menus, "떡볶이", min_co_count=2)
    assert all(r.menu_name != "특이메뉴" for r in results)


def test_no_one_ate_target_menu_returns_empty():
    employee_menus = {"E1": {"A"}, "E2": {"B"}}
    assert compute_menu_affinity(employee_menus, "떡볶이") == []


def test_empty_input_returns_empty():
    assert compute_menu_affinity({}, "떡볶이") == []


def test_results_sorted_by_lift_descending():
    employee_menus = {
        "E1": {"떡볶이", "짜장면", "순대"},
        "E2": {"떡볶이", "짜장면"},
        "E3": {"떡볶이", "순대"},
        "E4": {"떡볶이"},
        "E5": {"짜장면", "순대", "돈까스"},
        "E6": {"돈까스"},
    }
    results = compute_menu_affinity(employee_menus, "떡볶이", min_co_count=1)
    lifts = [r.lift for r in results]
    assert lifts == sorted(lifts, reverse=True)


def test_top_n_limits_results():
    employee_menus = {f"E{i}": {"떡볶이", f"메뉴{i}"} for i in range(20)}
    results = compute_menu_affinity(employee_menus, "떡볶이", min_co_count=1, top_n=5)
    assert len(results) == 5


def test_top_menu_pairs_ranks_most_common_pair_first():
    # 떡볶이+짜장면 쌍이 4번으로 가장 흔함
    employee_menus = {
        "E1": {"떡볶이", "짜장면"},
        "E2": {"떡볶이", "짜장면"},
        "E3": {"떡볶이", "짜장면"},
        "E4": {"떡볶이", "짜장면"},
        "E5": {"돈까스", "순대"},
        "E6": {"돈까스", "순대"},
    }
    results = compute_top_menu_pairs(employee_menus, min_co_count=2)
    top = results[0]
    assert {top.menu_a, top.menu_b} == {"떡볶이", "짜장면"}
    assert top.co_count == 4


def test_top_menu_pairs_min_co_count_filters():
    employee_menus = {
        "E1": {"A", "B"},
        "E2": {"C", "D"},
        "E3": {"C", "D"},
        "E4": {"C", "D"},
    }
    results = compute_top_menu_pairs(employee_menus, min_co_count=2)
    pairs = [{r.menu_a, r.menu_b} for r in results]
    assert {"A", "B"} not in pairs  # co_count=1이라 걸러짐
    assert {"C", "D"} in pairs


def test_top_menu_pairs_top_n_limits_results():
    employee_menus = {f"E{i}": {"떡볶이", f"메뉴{i}", "짜장면"} for i in range(20)}
    results = compute_top_menu_pairs(employee_menus, min_co_count=1, top_n=5)
    assert len(results) == 5


def test_top_menu_pairs_empty_input_returns_empty():
    assert compute_top_menu_pairs({}) == []


def test_top_menu_pairs_lift_matches_formula():
    employee_menus = {
        "E1": {"A", "B"},
        "E2": {"A", "B"},
        "E3": {"A"},
        "E4": {"B"},
    }
    results = compute_top_menu_pairs(employee_menus, min_co_count=1)
    pair = next(r for r in results if {r.menu_a, r.menu_b} == {"A", "B"})
    # lift(A,B) = co_count * total / (count_A * count_B) = 2 * 4 / (3 * 3)
    assert pair.lift == pytest.approx(2 * 4 / (3 * 3))


def test_is_obvious_pair_true_for_near_identical_vectors():
    # 부대찌개-참치김치찌개처럼 같은 카테고리(둘 다 매운맛/국물 강함)
    a = [0.9, 0.1, 0.5, 0.2, 0.3, 0.4, 0.3, 0.1, 0.9, 0.3]
    b = [0.88, 0.12, 0.52, 0.18, 0.31, 0.42, 0.29, 0.1, 0.87, 0.28]
    assert is_obvious_pair(a, b) is True


def test_is_obvious_pair_false_for_different_vectors():
    a = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert is_obvious_pair(a, b) is False


def test_is_obvious_pair_none_when_vector_missing():
    assert is_obvious_pair(None, [0.5] * 10) is None
    assert is_obvious_pair([0.5] * 10, None) is None

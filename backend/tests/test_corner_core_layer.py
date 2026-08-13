from app.services.corner_core_layer import classify_corner_core_layer


def test_meets_visit_count_and_share_is_core_layer():
    # 코너1을 5번(전체 6번 중 5번, 약 0.83) 방문 — 방문횟수·비중 둘 다 충족
    counts = {"E1": {1: 5, 2: 1}}
    results = classify_corner_core_layer(counts, corner_id=1, min_visit_count=3, min_share=0.3)
    assert len(results) == 1
    assert results[0].employee_id == "E1"
    assert results[0].corner_visit_count == 5
    assert results[0].total_visit_count == 6


def test_low_visit_count_excluded_even_if_share_high():
    # 코너1을 2번만 방문(전체도 2번, 비중 1.0) — 방문횟수 미달로 제외
    counts = {"E1": {1: 2}}
    results = classify_corner_core_layer(counts, corner_id=1, min_visit_count=3, min_share=0.3)
    assert results == []


def test_low_share_excluded_even_if_visit_count_high():
    # 코너1을 4번 방문했지만 전체 20번 중 일부(비중 0.2) — 헤비유저라 여러 코너에 다님
    counts = {"E1": {1: 4, 2: 8, 3: 8}}
    results = classify_corner_core_layer(counts, corner_id=1, min_visit_count=3, min_share=0.3)
    assert results == []


def test_empty_input_returns_empty():
    assert classify_corner_core_layer({}, corner_id=1) == []


def test_employee_with_no_visits_to_target_corner_excluded():
    counts = {"E1": {2: 5, 3: 5}}
    results = classify_corner_core_layer(counts, corner_id=1, min_visit_count=1, min_share=0.01)
    assert results == []


def test_results_sorted_by_share_then_visit_count_descending():
    counts = {
        "E1": {1: 3, 2: 1},  # share 0.75
        "E2": {1: 5, 2: 5},  # share 0.5
        "E3": {1: 9, 2: 1},  # share 0.9
    }
    results = classify_corner_core_layer(counts, corner_id=1, min_visit_count=1, min_share=0.1)
    assert [r.employee_id for r in results] == ["E3", "E1", "E2"]

from app.services.weekly_menu_prediction import (
    combine_menu_multiplier,
    compute_core_layer_menu_signal,
    compute_expected_wait_minutes,
    compute_predicted_share,
)


def test_combine_menu_multiplier_geometric_mean_of_both_signals():
    # share_multiplier=1.44, throughput_ratio=1.0 -> sqrt(1.44*1.0) = 1.2
    assert round(combine_menu_multiplier(1.44, 1.0), 4) == 1.2


def test_combine_menu_multiplier_uses_only_available_signal():
    assert combine_menu_multiplier(1.3, None) == 1.3
    assert combine_menu_multiplier(None, 0.8) == 0.8


def test_combine_menu_multiplier_none_when_no_signal():
    assert combine_menu_multiplier(None, None) is None
    assert combine_menu_multiplier(0, None) is None  # 0 이하는 신호 없음으로 취급


def test_compute_predicted_share_normalizes_across_corners():
    shares = compute_predicted_share({1: 30.0, 2: 10.0, 3: 60.0})
    assert shares[1] == 0.3
    assert shares[2] == 0.1
    assert shares[3] == 0.6


def test_compute_predicted_share_handles_zero_total():
    shares = compute_predicted_share({1: 0.0, 2: 0.0})
    assert shares == {1: 0.0, 2: 0.0}


def test_compute_core_layer_menu_signal_counts_eaters_each_side():
    core_ids = {"C1", "C2"}
    all_ids = {"C1", "C2", "N1", "N2", "N3"}
    employee_menus = {
        "C1": {"제육볶음", "김치"},
        "C2": {"된장찌개"},
        "N1": {"제육볶음"},
        "N2": {"돈까스"},
        "N3": set(),
    }
    signal = compute_core_layer_menu_signal(core_ids, all_ids, employee_menus, "제육볶음")
    assert signal.core_employee_count == 2
    assert signal.core_menu_eaters == 1
    assert signal.non_core_employee_count == 3
    assert signal.non_core_menu_eaters == 1


def test_compute_expected_wait_minutes_zero_when_demand_fits_peak_capacity():
    # 피크 40분 동안 분당 1명씩(=40명) 처리 가능한데, 피크에 몰릴 것으로
    # 추정되는 인원(예상 식수 80명 중 50%인 40명)이 딱 그만큼이라 대기 없음.
    wait = compute_expected_wait_minutes(
        predicted_headcount=80.0, effective_throughput=1.0, peak_share_ratio=0.5, peak_window_minutes=40.0
    )
    assert wait == 0.0


def test_compute_expected_wait_minutes_positive_when_demand_exceeds_peak_capacity():
    # 피크 용량은 40명(분당 1명×40분)인데, 피크에 몰릴 것으로 추정되는 인원은
    # 100명×0.6=60명 — 초과 20명을 분당 1명으로 마저 처리하려면 20분 더 걸림.
    wait = compute_expected_wait_minutes(
        predicted_headcount=100.0, effective_throughput=1.0, peak_share_ratio=0.6, peak_window_minutes=40.0
    )
    assert wait == 20.0


def test_compute_expected_wait_minutes_none_without_throughput_or_ratio():
    assert compute_expected_wait_minutes(50.0, None, 0.5, 40.0) is None
    assert compute_expected_wait_minutes(50.0, 0.0, 0.5, 40.0) is None
    assert compute_expected_wait_minutes(50.0, 1.0, None, 40.0) is None

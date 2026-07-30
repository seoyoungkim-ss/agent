from app.services.improvement_points import (
    select_congestion_points,
    select_satisfaction_points,
    select_voe_points,
)


def test_select_congestion_points_flags_high_traffic_low_throughput_corner():
    corners = [
        {"corner_name": "한식", "headcount_total": 500, "avg_peak_throughput_per_min": 0.5},
        {"corner_name": "일품", "headcount_total": 480, "avg_peak_throughput_per_min": 3.0},
        {"corner_name": "분식", "headcount_total": 50, "avg_peak_throughput_per_min": 5.0},
    ]
    points = select_congestion_points(corners)
    assert len(points) == 1
    assert points[0].axis == "congestion"
    assert "한식" in points[0].title
    assert points[0].severity == "warning"


def test_select_congestion_points_empty_when_not_enough_data():
    assert select_congestion_points([{"corner_name": "한식", "headcount_total": 10, "avg_peak_throughput_per_min": 1.0}]) == []
    assert select_congestion_points([]) == []


def test_select_satisfaction_points_picks_needs_improvement_by_share_desc():
    menu_rows = [
        {"menu_name": "A", "corner_name": "한식", "quadrant": "개선시급", "share_of_traffic": 0.05, "adjusted_score": 2.5},
        {"menu_name": "B", "corner_name": "일품", "quadrant": "개선시급", "share_of_traffic": 0.2, "adjusted_score": 2.8},
        {"menu_name": "C", "corner_name": "한식", "quadrant": "인기메뉴", "share_of_traffic": 0.5, "adjusted_score": 4.5},
    ]
    points = select_satisfaction_points(menu_rows, top_n=2)
    assert [p.title for p in points] == ["B (일품) 만족도 개선 필요", "A (한식) 만족도 개선 필요"]
    assert all(p.axis == "satisfaction" and p.severity == "critical" for p in points)


def test_select_voe_points_prefers_largest_month_over_month_increase():
    current = {"categories": [{"category": "맛", "count": 5}, {"category": "위생", "count": 12}, {"category": "기타", "count": 20}]}
    prior = {"categories": [{"category": "맛", "count": 4}, {"category": "위생", "count": 3}]}
    points = select_voe_points(current, prior)
    assert len(points) == 1
    assert "위생" in points[0].title
    assert "9건" in points[0].detail


def test_select_voe_points_falls_back_to_top_count_without_prior_month():
    current = {"categories": [{"category": "맛", "count": 3}, {"category": "위생", "count": 8}]}
    points = select_voe_points(current, None)
    assert len(points) == 1
    assert "위생" in points[0].title


def test_select_voe_points_empty_when_no_comments():
    assert select_voe_points({"categories": []}, None) == []

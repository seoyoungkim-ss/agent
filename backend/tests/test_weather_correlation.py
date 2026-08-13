from app.services.weather_correlation import pearson_correlation


def test_perfect_positive_correlation():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert pearson_correlation(xs, ys) == 1.0


def test_perfect_negative_correlation():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [50.0, 40.0, 30.0, 20.0, 10.0]
    assert pearson_correlation(xs, ys) == -1.0


def test_zero_variance_in_x_returns_none():
    """모든 날 기온이 같으면(예: 실측이 죄다 같은 값) 상관계수를 정의할 수 없다."""
    assert pearson_correlation([20.0, 20.0, 20.0], [10.0, 20.0, 30.0]) is None


def test_zero_variance_in_y_returns_none():
    assert pearson_correlation([10.0, 20.0, 30.0], [5.0, 5.0, 5.0]) is None


def test_fewer_than_two_samples_returns_none():
    assert pearson_correlation([1.0], [2.0]) is None
    assert pearson_correlation([], []) is None


def test_mismatched_lengths_returns_none():
    assert pearson_correlation([1.0, 2.0], [1.0]) is None

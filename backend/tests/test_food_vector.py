from app.services.food_vector import FOOD_VECTOR_DIMENSIONS, compute_average_food_vector, describe_average_bias


def test_compute_average_food_vector_averages_each_dimension():
    dim = len(FOOD_VECTOR_DIMENSIONS)
    vectors = [
        [1.0, 0.0] + [0.0] * (dim - 2),
        [0.0, 1.0] + [0.0] * (dim - 2),
    ]
    average = compute_average_food_vector(vectors)
    assert average[0] == 0.5
    assert average[1] == 0.5
    assert all(x == 0.0 for x in average[2:])


def test_compute_average_food_vector_empty_returns_zeros():
    assert compute_average_food_vector([]) == [0.0] * len(FOOD_VECTOR_DIMENSIONS)


def test_describe_average_bias_calls_out_standout_dimensions():
    dim = len(FOOD_VECTOR_DIMENSIONS)
    average = [0.9, 0.85] + [0.5] * (dim - 2)  # spicy, sweet 순으로 중립(0.5)보다 뚜렷이 높음
    text = describe_average_bias(average)
    assert "매운맛" in text
    assert "단맛" in text


def test_describe_average_bias_balanced_when_no_standout_dimension():
    average = [0.5] * len(FOOD_VECTOR_DIMENSIONS)
    text = describe_average_bias(average)
    assert "편향" in text

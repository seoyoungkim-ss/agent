import numpy as np

from app.services.taste_clustering import cluster_vectors, generate_cluster_label


def test_cluster_vectors_separates_distinct_groups():
    # 두 그룹: 매운맛(dim0) 높은 그룹 vs 낮은 그룹
    group_a = [[0.9, 0.1] for _ in range(5)]
    group_b = [[0.1, 0.9] for _ in range(5)]
    result = cluster_vectors(group_a + group_b, k=2)

    labels_a = set(result.labels[:5])
    labels_b = set(result.labels[5:])
    assert len(labels_a) == 1
    assert len(labels_b) == 1
    assert labels_a != labels_b


def test_cluster_vectors_returns_centroid_per_cluster():
    vectors = [[0.9, 0.1]] * 4 + [[0.1, 0.9]] * 4
    result = cluster_vectors(vectors, k=2)
    assert len(result.centroids) == 2
    assert len(result.centroids[0]) == 2


def test_label_picks_standout_dimension():
    dims = ["spicy", "sweet", "protein"]
    labels_ko = {"spicy": "매운맛", "sweet": "단맛", "protein": "단백질"}
    centroid = [0.8, 0.3, 0.35]
    global_mean = [0.3, 0.3, 0.3]
    label = generate_cluster_label(
        centroid, global_mean, dimensions=dims, labels_ko=labels_ko, threshold=0.12
    )
    assert label == "매운맛 선호형"


def test_label_picks_up_to_two_standout_dimensions_in_order():
    dims = ["spicy", "sweet", "protein"]
    labels_ko = {"spicy": "매운맛", "sweet": "단맛", "protein": "단백질"}
    centroid = [0.9, 0.31, 0.7]  # spicy(+0.6), protein(+0.4), sweet(+0.01 이하 threshold)
    global_mean = [0.3, 0.3, 0.3]
    label = generate_cluster_label(
        centroid, global_mean, dimensions=dims, labels_ko=labels_ko, threshold=0.12, max_dimensions=2
    )
    assert label == "매운맛·단백질 선호형"


def test_label_balanced_when_nothing_stands_out():
    dims = ["spicy", "sweet", "protein"]
    labels_ko = {"spicy": "매운맛", "sweet": "단맛", "protein": "단백질"}
    centroid = [0.32, 0.31, 0.29]
    global_mean = [0.3, 0.3, 0.3]
    label = generate_cluster_label(
        centroid, global_mean, dimensions=dims, labels_ko=labels_ko, threshold=0.12
    )
    assert label == "균형형"


def test_label_deterministic_for_same_input():
    dims = ["spicy", "sweet"]
    labels_ko = {"spicy": "매운맛", "sweet": "단맛"}
    centroid = [0.8, 0.3]
    global_mean = [0.3, 0.3]
    label1 = generate_cluster_label(centroid, global_mean, dimensions=dims, labels_ko=labels_ko)
    label2 = generate_cluster_label(centroid, global_mean, dimensions=dims, labels_ko=labels_ko)
    assert label1 == label2

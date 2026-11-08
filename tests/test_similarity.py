from code.week03.mini_rag.similarity import cosine, similarity_matrix, top_k


def test_cosine_basic():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0  # 零向量不除零


def test_cosine_dimension_mismatch():
    import pytest

    with pytest.raises(ValueError):
        cosine([1.0], [1.0, 2.0])


def test_matrix_symmetric_diagonal_one():
    vecs = [[1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    m = similarity_matrix(vecs)
    for i in range(3):
        assert m[i][i] == 1.0
        for j in range(3):
            assert m[i][j] == m[j][i]


def test_top_k_returns_sorted():
    matrix = [[1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    result = top_k([1.0, 0.0], matrix, k=2)
    assert len(result) == 2
    assert result[0][1] >= result[1][1]
    assert result[0][0] == 0

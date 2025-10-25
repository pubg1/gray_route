import pytest

from app.opensearch_matcher import OpenSearchMatcher


@pytest.mark.parametrize(
    "message, expected",
    [
        ("Field 'text_vector' is not knn_vector type.", True),
        ("field [text_vector] is not a knn_vector", True),
        ("Cannot run knn search on field [text_vector] if field is not knn_vector", True),
        ("random error", False),
    ],
)
def test_should_disable_vector_field(message: str, expected: bool) -> None:
    error = Exception(message)
    assert OpenSearchMatcher._should_disable_vector_field(error) is expected

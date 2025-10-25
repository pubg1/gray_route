from types import SimpleNamespace
from typing import Dict

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


def test_lookup_field_mapping_simple() -> None:
    properties = {
        "text_vector": {"type": "knn_vector", "dimension": 3},
        "text": {"type": "text"},
    }
    mapping = OpenSearchMatcher._lookup_field_mapping(properties, "text_vector")
    assert mapping == {"type": "knn_vector", "dimension": 3}


def test_lookup_field_mapping_nested() -> None:
    properties = {
        "doc": {
            "properties": {
                "text_vector": {"type": "knn_vector", "dimension": 3},
            }
        }
    }
    mapping = OpenSearchMatcher._lookup_field_mapping(properties, "doc.text_vector")
    assert mapping == {"type": "knn_vector", "dimension": 3}


def test_lookup_field_mapping_missing() -> None:
    properties = {"text": {"type": "text"}}
    mapping = OpenSearchMatcher._lookup_field_mapping(properties, "unknown")
    assert mapping is None


def test_is_knn_vector_mapping() -> None:
    assert OpenSearchMatcher._is_knn_vector_mapping({"type": "knn_vector"}) is True
    assert OpenSearchMatcher._is_knn_vector_mapping({"type": "dense_vector"}) is False
    assert OpenSearchMatcher._is_knn_vector_mapping(None) is False


def test_vector_field_is_configured_checks_mapping() -> None:
    mapping = {
        "cases_recovery": {
            "mappings": {
                "properties": {
                    "text_vector": {"type": "knn_vector", "dimension": 3}
                }
            }
        }
    }

    class DummyIndices:
        def __init__(self, data: Dict[str, object]):
            self._data = data

        def get_mapping(self, index: str) -> Dict[str, object]:
            assert index == "cases_recovery"
            return self._data

    matcher = object.__new__(OpenSearchMatcher)
    matcher.vector_field = "text_vector"
    matcher.client = SimpleNamespace(indices=DummyIndices(mapping))

    assert matcher._vector_field_is_configured() is True


def test_vector_field_is_configured_missing_field() -> None:
    mapping = {
        "cases_recovery": {
            "mappings": {
                "properties": {
                    "text": {"type": "text"},
                }
            }
        }
    }

    class DummyIndices:
        def __init__(self, data: Dict[str, object]):
            self._data = data

        def get_mapping(self, index: str) -> Dict[str, object]:
            assert index == "cases_recovery"
            return self._data

    matcher = object.__new__(OpenSearchMatcher)
    matcher.vector_field = "text_vector"
    matcher.client = SimpleNamespace(indices=DummyIndices(mapping))

    assert matcher._vector_field_is_configured() is False


def test_vector_field_is_configured_on_error_keeps_semantic() -> None:
    class ErrorIndices:
        def get_mapping(self, index: str) -> Dict[str, object]:
            raise RuntimeError("boom")

    matcher = object.__new__(OpenSearchMatcher)
    matcher.vector_field = "text_vector"
    matcher.client = SimpleNamespace(indices=ErrorIndices())

    assert matcher._vector_field_is_configured() is True

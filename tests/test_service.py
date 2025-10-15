from __future__ import annotations

from types import SimpleNamespace

import importlib.util
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from failure_search.service import FailureSearchService, _normalise_filters


class FakeEmbedder:
    dimension = 3

    def __init__(self) -> None:
        self.seen_texts: list[str] = []

    def embed(self, text: str):
        self.seen_texts.append(text)
        length = float(len(text))
        return [length, length / 2.0, length / 3.0]


class FakeIndices:
    def __init__(self) -> None:
        self.created: tuple[str, dict] | None = None
        self.exists_called: list[str] = []

    def exists(self, index: str) -> bool:
        self.exists_called.append(index)
        return False

    def create(self, index: str, body: dict) -> None:
        self.created = (index, body)


class FakeClient:
    def __init__(self) -> None:
        self.indices = FakeIndices()
        self.indexed: list[tuple[str, str, dict, bool]] = []
        self.last_query: dict | None = None
        self.search_response: dict = {"hits": {"hits": []}}

    def index(self, *, index: str, id: str, body: dict, refresh: bool) -> None:
        self.indexed.append((index, id, body, refresh))

    def search(self, *, index: str, body: dict, params: dict) -> dict:
        self.last_query = {"index": index, "body": body, "params": params}
        return self.search_response


@pytest.fixture(autouse=True)
def patch_dependency_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "failure_search.service._ensure_opensearch_dependency", lambda: None
    )
    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str):
        if name.startswith("opensearchpy") or name == "sentence_transformers":
            return SimpleNamespace()
        return original_find_spec(name)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)


def test_normalise_filters() -> None:
    filters = {"system": "control", "severity": ["S1", "S2"], "ignored": None}
    clauses = _normalise_filters(filters)
    assert {"term": {"system": "control"}} in clauses
    assert {"terms": {"severity": ["S1", "S2"]}} in clauses
    assert all("ignored" not in clause for clause in clauses)


def test_ensure_index_builds_knn_mapping() -> None:
    client = FakeClient()
    embedder = FakeEmbedder()
    service = FailureSearchService(client=client, index_name="failures", embedder=embedder)

    service.ensure_index()

    created = client.indices.created
    assert created is not None
    index, body = created
    assert index == "failures"
    assert body["settings"]["index"]["knn"] is True
    assert body["mappings"]["properties"]["embedding"]["dimension"] == embedder.dimension


def test_index_failure_embeds_combined_text() -> None:
    client = FakeClient()
    embedder = FakeEmbedder()
    service = FailureSearchService(client=client, index_name="failures", embedder=embedder)

    service.index_failure(
        failure_id="F-1",
        title="风机故障",
        description="电流异常波动",
        metadata={"system": "风电"},
        refresh=True,
    )

    assert len(client.indexed) == 1
    _, _, document, refresh = client.indexed[0]
    assert refresh is True
    assert document["metadata"]["system"] == "风电"
    assert embedder.seen_texts[0].startswith("风机故障")
    assert "system: 风电" in embedder.seen_texts[0]


def test_search_builds_hybrid_script_query() -> None:
    client = FakeClient()
    embedder = FakeEmbedder()
    service = FailureSearchService(client=client, index_name="failures", embedder=embedder)
    service.lexical_weight = 2.0
    service.vector_weight = 0.5

    response = service.search_failures("轴承过热", size=5, filters={"metadata.system": "风电"})

    assert response == client.search_response
    assert client.last_query is not None
    body = client.last_query["body"]
    script = body["query"]["script_score"]["script"]
    assert "cosineSimilarity" in script["source"]
    assert script["params"]["lexical_weight"] == 2.0
    assert script["params"]["vector_weight"] == 0.5
    assert body["size"] == 5

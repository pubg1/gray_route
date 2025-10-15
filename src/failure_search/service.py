"""High level service for hybrid failure knowledge search on OpenSearch."""
from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from .embeddings import BaseEmbedder, SentenceTransformerEmbedder


def _ensure_opensearch_dependency() -> None:
    if importlib.util.find_spec("opensearchpy") is None:  # pragma: no cover - guard
        raise RuntimeError(
            "opensearch-py is required. Install it with `pip install opensearch-py`."
        )


def _normalise_filters(filters: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not filters:
        return []

    clauses: list[Mapping[str, Any]] = []
    for field, value in filters.items():
        if value is None:
            continue
        if isinstance(value, (set, list, tuple)):
            clauses.append({"terms": {field: list(value)}})
        else:
            clauses.append({"term": {field: value}})
    return clauses


@dataclass
class FailureSearchService:
    """Provide hybrid (lexical + semantic) search over failure cases."""

    client: Any
    index_name: str
    embedder: BaseEmbedder | None = None
    lexical_weight: float = 1.0
    vector_weight: float = 1.0

    def __post_init__(self) -> None:
        if self.embedder is None:
            self.embedder = SentenceTransformerEmbedder()

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------
    def ensure_index(self, *, shards: int = 1, replicas: int = 1) -> None:
        """Create the OpenSearch index with a vector field if it does not exist."""

        _ensure_opensearch_dependency()

        if self.client.indices.exists(self.index_name):
            return

        settings = {
            "settings": {
                "index": {
                    "knn": True,
                    "number_of_shards": shards,
                    "number_of_replicas": replicas,
                },
                "knn.algo_param.ef_search": 100,
            },
            "mappings": {
                "properties": {
                    "failure_id": {"type": "keyword"},
                    "title": {
                        "type": "text",
                        "fields": {"raw": {"type": "keyword"}},
                    },
                    "description": {"type": "text"},
                    "metadata": {
                        "type": "object",
                        "dynamic": True,
                    },
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": int(self.embedder.dimension),
                        "method": {
                            "engine": "nmslib",
                            "space_type": "cosinesimil",
                            "name": "hnsw",
                            "parameters": {"ef_construction": 256, "m": 48},
                        },
                    },
                }
            },
        }

        self.client.indices.create(index=self.index_name, body=settings)

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------
    def _text_for_embedding(self, title: str, description: str, metadata: Mapping[str, Any] | None) -> str:
        meta_text = "\n".join(f"{key}: {value}" for key, value in (metadata or {}).items())
        return "\n".join([part for part in [title, description, meta_text] if part])

    def _document_from_input(
        self,
        *,
        failure_id: str,
        title: str,
        description: str,
        metadata: Mapping[str, Any] | None,
    ) -> MutableMapping[str, Any]:
        assert self.embedder is not None
        embedding_input = self._text_for_embedding(title, description, metadata)
        embedding = list(self.embedder.embed(embedding_input))

        document: MutableMapping[str, Any] = {
            "failure_id": failure_id,
            "title": title,
            "description": description,
            "embedding": embedding,
        }
        if metadata:
            document["metadata"] = dict(metadata)
        return document

    def index_failure(
        self,
        *,
        failure_id: str,
        title: str,
        description: str,
        metadata: Mapping[str, Any] | None = None,
        refresh: bool = False,
    ) -> None:
        """Index or update a single failure case."""

        document = self._document_from_input(
            failure_id=failure_id,
            title=title,
            description=description,
            metadata=metadata,
        )
        self.client.index(index=self.index_name, id=failure_id, body=document, refresh=refresh)

    def bulk_index(
        self,
        failures: Iterable[Mapping[str, Any]],
        *,
        refresh: bool = False,
    ) -> None:
        """Bulk index multiple failure cases with embeddings."""

        _ensure_opensearch_dependency()
        helpers_spec = importlib.util.find_spec("opensearchpy.helpers")
        if helpers_spec is None:  # pragma: no cover - guard
            raise RuntimeError("Bulk indexing requires opensearch-py.helpers to be installed.")

        from opensearchpy.helpers import bulk  # type: ignore

        actions = []
        for failure in failures:
            document = self._document_from_input(
                failure_id=str(failure["failure_id"]),
                title=str(failure.get("title", "")),
                description=str(failure.get("description", "")),
                metadata=failure.get("metadata"),
            )
            actions.append(
                {
                    "_op_type": "index",
                    "_index": self.index_name,
                    "_id": document["failure_id"],
                    "_source": document,
                }
            )

        bulk(self.client, actions, refresh=refresh)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------
    def _build_base_query(
        self,
        query_text: str,
        filters: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]:
        filter_clauses = _normalise_filters(filters)
        bool_query: MutableMapping[str, Any] = {"filter": filter_clauses}
        if self.lexical_weight > 0:
            bool_query["must"] = [
                {
                    "multi_match": {
                        "query": query_text,
                        "fields": ["title^2", "description", "metadata.*"],
                        "type": "most_fields",
                    }
                }
            ]
        else:
            bool_query["must"] = [{"match_all": {}}]
        return {"bool": bool_query}

    def _build_hybrid_query(
        self,
        query_text: str,
        *,
        size: int,
        filters: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]:
        assert self.embedder is not None
        embedding = list(self.embedder.embed(query_text))
        base_query = self._build_base_query(query_text, filters)

        return {
            "size": size,
            "query": {
                "script_score": {
                    "query": base_query,
                    "script": {
                        "source": (
                            "params.lexical_weight * _score + "
                            "params.vector_weight * (cosineSimilarity(params.query_vector, 'embedding') + params.offset)"
                        ),
                        "params": {
                            "query_vector": embedding,
                            "lexical_weight": float(self.lexical_weight),
                            "vector_weight": float(self.vector_weight),
                            "offset": 1.0,
                        },
                    },
                }
            },
        }

    def search_failures(
        self,
        query_text: str,
        *,
        size: int = 10,
        filters: Mapping[str, Any] | None = None,
        source_fields: Sequence[str] | None = None,
    ) -> Mapping[str, Any]:
        """Perform a hybrid search across failure descriptions."""

        body = self._build_hybrid_query(query_text, size=size, filters=filters)
        params: dict[str, Any] = {}
        if source_fields is not None:
            params["_source"] = list(source_fields)

        response = self.client.search(index=self.index_name, body=body, params=params)
        return response


__all__ = ["FailureSearchService"]

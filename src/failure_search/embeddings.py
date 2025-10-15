"""Utilities for turning text into vector embeddings suitable for OpenSearch."""
from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from typing import Any, Iterable, Protocol, Sequence


class BaseEmbedder(Protocol):
    """Protocol that all embedders used by :class:`FailureSearchService` must follow."""

    @property
    def dimension(self) -> int:
        """Return the dimensionality of the embedding space."""

    def embed(self, text: str) -> Sequence[float]:
        """Return an embedding vector for the provided text."""

    def embed_many(self, texts: Iterable[str]) -> Sequence[Sequence[float]]:
        """Return embeddings for a batch of texts."""


@dataclass
class SentenceTransformerEmbedder:
    """Embedder backed by a SentenceTransformer model.

    The model is loaded lazily so that unit tests can provide a lightweight fake
    embedder without incurring the cost of downloading large transformer
    weights.  Embeddings are L2-normalised to make cosine similarity work well
    with OpenSearch's ``cosineSimilarity`` script.
    """

    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    device: str | None = None

    _model: Any | None = None
    _dimension: int | None = None

    def _load_model(self) -> "SentenceTransformer":
        if self._model is None:
            if importlib.util.find_spec("sentence_transformers") is None:  # pragma: no cover - guard
                raise RuntimeError(
                    "sentence-transformers is required to build semantic embeddings. "
                    "Install it with `pip install sentence-transformers`."
                )

            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._dimension = int(self._model.get_sentence_embedding_dimension())
        return self._model

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._load_model()
        assert self._dimension is not None
        return self._dimension

    def embed(self, text: str) -> Sequence[float]:
        model = self._load_model()
        vector = model.encode(text, normalize_embeddings=True)
        return [float(v) for v in vector]

    def embed_many(self, texts: Iterable[str]) -> Sequence[Sequence[float]]:
        model = self._load_model()
        vectors = model.encode(list(texts), normalize_embeddings=True)
        return [[float(v) for v in vector] for vector in vectors]


__all__ = ["BaseEmbedder", "SentenceTransformerEmbedder"]

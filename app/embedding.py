
from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List
from .config import get_settings
class Embedder:
    def __init__(self, model_name: str):
        self.model = SentenceTransformer(model_name, trust_remote_code=True)
    def encode(self, texts: List[str]) -> np.ndarray:
        emb = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.array(emb, dtype=np.float32)
_embedder = None
def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        settings = get_settings()
        _embedder = Embedder(settings.embedding_model)
    return _embedder

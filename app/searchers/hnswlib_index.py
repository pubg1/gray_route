
import os, json, hnswlib, numpy as np
from typing import List, Dict, Any
from ..embedding import get_embedder
from ..config import get_settings
from ..utils.data_loader import iter_records

class HNSWSearcher:
    def __init__(self, data_path: str, index_path: str):
        self.settings = get_settings()
        self.data_path = data_path
        self.index_path = index_path
        self.embedder = get_embedder()
        self.data = list(iter_records(self.data_path))
        self.texts = [d.get('text', '') for d in self.data]

        self.dim = self.embedder.encode(['test']).shape[1]
        self.index = hnswlib.Index(space='cosine', dim=self.dim)
        if os.path.exists(self.index_path):
            self.index.load_index(self.index_path)
            if self.index.element_count != len(self.data):
                self._rebuild()
        else:
            self._rebuild()
    def _rebuild(self):
        vecs = self.embedder.encode(self.texts)
        self.index.init_index(max_elements=len(self.data), ef_construction=200, M=32)
        self.index.add_items(vecs, np.arange(len(self.data)))
        self.index.set_ef(80)
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        self.index.save_index(self.index_path)
    def knn(self, query: str, topk: int = 50) -> List[Dict[str, Any]]:
        qv = self.embedder.encode([query])
        labels, dists = self.index.knn_query(qv, k=min(topk, len(self.data)))
        labels = labels[0].tolist()
        sims = (1 - dists[0]).tolist()
        hits = []
        for idx, sc in zip(labels, sims):
            row = self.data[idx].copy()
            row['cosine'] = float(sc)
            hits.append(row)
        return hits

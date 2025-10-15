
# app/searchers/keyword_tfidf.py
import os, json, pickle
from typing import List, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

class KeywordSearcher:
    def __init__(self, data_path: str, cache_path: str):
        self.data: List[Dict[str, Any]] = []
        with open(data_path, 'r', encoding='utf-8') as f:
            for line in f:
                self.data.append(json.loads(line))

        # 只保留有内容的文本，避免空列表
        self.texts = [d.get('text', '').strip() for d in self.data if d.get('text', '').strip()]
        if not self.texts:
            raise ValueError(f"没有可用文本：{data_path}")

        self.cache_path = cache_path
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, 'rb') as pf:
                    self.vectorizer, self.tfidf = pickle.load(pf)
            except Exception:
                self._fit()
        else:
            self._fit()

    def _fit(self):
        # 关键：中文用字符 n-gram，而不是默认英文词切分
        self.vectorizer = TfidfVectorizer(
            analyzer="char",        # 按字符
            ngram_range=(2, 4),     # 2~4 字 n-gram，兼顾召回与速度
            min_df=1,
            max_features=200_000
        )
        self.tfidf = self.vectorizer.fit_transform(self.texts)

        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        try:
            with open(self.cache_path, 'wb') as pf:
                pickle.dump((self.vectorizer, self.tfidf), pf)
        except Exception:
            pass

    def search(self, query: str, topk: int = 50) -> List[Dict[str, Any]]:
        q_vec = self.vectorizer.transform([query])
        scores = linear_kernel(q_vec, self.tfidf).ravel()
        top_idx = scores.argsort()[::-1][:topk]
        hits: List[Dict[str, Any]] = []
        for i in top_idx:
            row = self.data[i].copy()
            row['bm25_score'] = float(scores[i]) * 20.0  # 与融合步的归一化一致
            hits.append(row)
        return hits


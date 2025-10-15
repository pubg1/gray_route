#!/usr/bin/env bash
set -euo pipefail
source .venv/bin/activate
python - << 'PY'
from app.config import get_settings
from app.searchers.hnswlib_index import HNSWSearcher
from app.searchers.keyword_tfidf import KeywordSearcher
s = get_settings()
print("[i] building/loading indexes ...")
HNSWSearcher(s.data_file, s.hnsw_index_path)
KeywordSearcher(s.data_file, s.tfidf_cache_path)
print("[OK] indexes ready at:", s.hnsw_index_path, s.tfidf_cache_path)
PY

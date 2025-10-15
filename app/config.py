
import os
from pydantic import BaseModel
from functools import lru_cache
from dotenv import load_dotenv
load_dotenv()
class Settings(BaseModel):
    openai_api_base: str = os.getenv("OPENAI_API_BASE", "").strip()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    pass_threshold: float = float(os.getenv("PASS_THRESHOLD", 0.84))
    gray_low_threshold: float = float(os.getenv("GRAY_LOW_THRESHOLD", 0.65))
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    reranker_model: str = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")
    data_file: str = os.getenv("DATA_FILE", "data/phenomena_sample.jsonl")
    hnsw_index_path: str = os.getenv("HNSW_INDEX_PATH", "data/hnsw_index.bin")
    tfidf_cache_path: str = os.getenv("TFIDF_CACHE_PATH", "data/tfidf.pkl")
@lru_cache()
def get_settings() -> Settings:
    return Settings()


import os
from typing import Dict

from functools import lru_cache
from dotenv import load_dotenv
from pydantic import BaseModel

from .utils.calibration import load_calibration_profile, normalize_weight_mapping


load_dotenv()


class FusionWeights(BaseModel):
    rerank: float = 0.55
    semantic: float = 0.20
    keyword: float = 0.10
    knowledge: float = 0.10
    popularity: float = 0.05

    def normalized(self) -> "FusionWeights":
        weights = normalize_weight_mapping(self.dict(), defaults=self.dict())
        return FusionWeights(**weights)

    def as_dict(self) -> Dict[str, float]:
        return self.dict()


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
    score_calibration_path: str = os.getenv("SCORE_CALIBRATION_PATH", "").strip()
    fusion_weights: FusionWeights = FusionWeights()

    def __init__(self, **data):
        super().__init__(**data)
        self._apply_env_weight_overrides()
        self._apply_calibration_profile()

    def _apply_env_weight_overrides(self) -> None:
        env_mapping = {}
        for key in ["RERANK", "SEMANTIC", "KEYWORD", "KNOWLEDGE", "POPULARITY"]:
            value = os.getenv(f"FUSION_{key}_WEIGHT")
            if value is None:
                continue
            try:
                env_mapping[key.lower()] = float(value)
            except (TypeError, ValueError):
                continue
        if env_mapping:
            self.fusion_weights = self.fusion_weights.copy(update=env_mapping)
        self.fusion_weights = self.fusion_weights.normalized()

    def _apply_calibration_profile(self) -> None:
        profile = load_calibration_profile(self.score_calibration_path)
        if not profile:
            return
        if "pass_threshold" in profile:
            try:
                self.pass_threshold = float(profile["pass_threshold"])
            except (TypeError, ValueError):
                pass
        if "gray_low_threshold" in profile:
            try:
                self.gray_low_threshold = float(profile["gray_low_threshold"])
            except (TypeError, ValueError):
                pass
        fusion_raw = profile.get("fusion_weights")
        if isinstance(fusion_raw, dict):
            weights = normalize_weight_mapping(fusion_raw, defaults=self.fusion_weights.as_dict())
            self.fusion_weights = FusionWeights(**weights)


@lru_cache()
def get_settings() -> Settings:
    return Settings()

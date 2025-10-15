
from typing import List, Optional
from pydantic import BaseModel
class Candidate(BaseModel):
    id: str
    text: str
    system: Optional[str] = None
    part: Optional[str] = None
    tags: Optional[List[str]] = None
    popularity: Optional[float] = 0.0
    bm25_score: Optional[float] = None
    cosine: Optional[float] = None
    rerank_score: Optional[float] = None
    final_score: Optional[float] = None
    why: Optional[List[str]] = None
class MatchResponse(BaseModel):
    query: str
    top: List[Candidate]
    decision: dict

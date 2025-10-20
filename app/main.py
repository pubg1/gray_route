
import asyncio
import logging
import os
from typing import List, Optional

import numpy as np
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .llm_router import closed_set_pick
from .models import Candidate, MatchResponse
from .reranker import get_reranker
from .searchers.hnswlib_index import HNSWSearcher
from .searchers.keyword_tfidf import KeywordSearcher
from .utils.calibration import clamp, compute_stats, logistic_from_stats
from .utils.normalize import normalize_query

# 尝试导入 OpenSearch 匹配器
try:
    from .opensearch_matcher import opensearch_matcher
    OPENSEARCH_AVAILABLE = opensearch_matcher is not None
except ImportError:
    OPENSEARCH_AVAILABLE = False
    opensearch_matcher = None

OPENSEARCH_SEMANTIC_AVAILABLE = bool(
    OPENSEARCH_AVAILABLE and getattr(opensearch_matcher, "semantic_available", False)
)

logger = logging.getLogger(__name__)

app = FastAPI(default_response_class=ORJSONResponse)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 如需限制，可改成 ["http://127.0.0.1:8080"]
    allow_methods=["*"],
    allow_headers=["*"],
)
settings = get_settings()
_hnsw = HNSWSearcher(settings.data_file, settings.hnsw_index_path)
_kw = KeywordSearcher(settings.data_file, settings.tfidf_cache_path)
@app.get("/health")
def health():
    sources = ["local_hnsw", "local_tfidf"]
    if OPENSEARCH_AVAILABLE:
        sources.append("opensearch")
        if OPENSEARCH_SEMANTIC_AVAILABLE:
            sources.append("opensearch_semantic")
    return {
        "status": "ok",
        "opensearch_available": OPENSEARCH_AVAILABLE,
        "semantic_available": OPENSEARCH_SEMANTIC_AVAILABLE,
        "data_sources": sources
    }
@app.get("/match", response_model=MatchResponse)
async def match(q: str = Query(..., description="用户查询"), system: Optional[str] = None, part: Optional[str] = None,
                model: Optional[str] = None, year: Optional[str] = None, topk_vec: int = 50, topk_kw: int = 50,
                topn_return: int = 3):
    query = normalize_query(q)
    reranker = get_reranker()
    knn_task = asyncio.to_thread(_hnsw.knn, query, topk=topk_vec)
    bm25_task = asyncio.to_thread(_kw.search, query, topk=topk_kw)
    knn_hits, bm25_hits = await asyncio.gather(knn_task, bm25_task)
    seen = set(); pool: List[Candidate] = []
    for src in knn_hits + bm25_hits:
        cid = src.get("id", "")
        if cid in seen:
            for p in pool:
                if p.id == cid:
                    p.bm25_score = p.bm25_score or src.get("bm25_score")
                    p.cosine = p.cosine or src.get("cosine")
                    break
            continue
        seen.add(cid)
        pool.append(Candidate(id=cid, text=src.get("text",""), system=src.get("system"), part=src.get("part"),
                              tags=src.get("tags"), popularity=src.get("popularity", 0.0),
                              bm25_score=src.get("bm25_score"), cosine=src.get("cosine")))
    texts = [p.text for p in pool]
    rerank_scores = reranker.score(query, texts, batch_size=16) if texts else []
    for p, s in zip(pool, rerank_scores):
        p.rerank_score = float(s)

    rerank_stats = compute_stats(rerank_scores)
    bm25_raws = [p.bm25_score for p in pool if p.bm25_score is not None]
    bm25_stats = compute_stats(bm25_raws)
    cosine_raws = [p.cosine for p in pool if p.cosine is not None]
    cosine_stats = compute_stats(cosine_raws)
    def kg_prior(p: Candidate) -> float:
        prior = 0.0
        if system and p.system and system == p.system: prior += 1.0
        if part and p.part and part == p.part: prior += 0.5
        return min(1.0, prior)
    weights = settings.fusion_weights.as_dict()
    for p in pool:
        cos_raw = p.cosine or 0.0
        bm_raw = p.bm25_score or 0.0
        rer_raw = p.rerank_score or 0.0

        rer = logistic_from_stats(rer_raw, rerank_stats, fallback=rer_raw)
        bm = logistic_from_stats(bm_raw, bm25_stats, fallback=clamp(bm_raw / 20.0))
        cos = logistic_from_stats(cos_raw, cosine_stats, fallback=clamp(cos_raw))
        kg = kg_prior(p)
        raw_pop = max(0.0, float(p.popularity or 0.0))
        pop = clamp(np.log1p(raw_pop) / 5.0)

        p.final_score = (
            weights["rerank"] * rer
            + weights["semantic"] * cos
            + weights["keyword"] * bm
            + weights["knowledge"] * kg
            + weights["popularity"] * pop
        )

        why = []
        if rer >= 0.6:
            why.append("精排高分")
        if cos >= 0.4:
            why.append("语义近")
        if bm >= 0.2:
            why.append("关键词命中")
        if kg >= 1.0:
            why.append("系统一致")
        elif kg > 0.1:
            why.append("部件相近")
        if pop >= 0.5:
            why.append("热门案例")
        p.why = why
        p.rerank_score = rer
        p.bm25_score = bm
        p.cosine = cos
    pool.sort(key=lambda x: x.final_score or 0.0, reverse=True)
    top10 = pool[:10]
    decision = {"mode": "fallback", "chosen_id": None, "confidence": 0.0}
    if not top10:
        return MatchResponse(query=query, top=[], decision=decision)
    top1 = top10[0]; s = top1.final_score or 0.0
    PASS = settings.pass_threshold; GRAY = settings.gray_low_threshold
    if s >= PASS:
        decision = {"mode": "direct", "chosen_id": top1.id, "confidence": s}
        return MatchResponse(query=query, top=top10[:topn_return], decision=decision)
    if s >= GRAY:
        cand_list = [{"id": c.id, "text": c.text} for c in top10]
        out = await closed_set_pick(query, cand_list)
        chosen = out.get("chosen_id", "UNKNOWN"); conf = float(out.get("confidence", 0.0))
        if chosen != "UNKNOWN":
            chosen_c = next((c for c in top10 if c.id == chosen), top1)
            decision = {"mode": "llm", "chosen_id": chosen, "confidence": max(conf, chosen_c.final_score or 0.0)}
            return MatchResponse(query=query, top=top10[:topn_return], decision=decision)
    decision = {"mode": "fallback", "chosen_id": None, "confidence": float(s)}
    return MatchResponse(query=query, top=top10[:topn_return], decision=decision)

# OpenSearch 相关 API 端点
from pydantic import BaseModel

class OpenSearchRequest(BaseModel):
    q: str
    system: Optional[str] = None
    part: Optional[str] = None
    vehicletype: Optional[str] = None
    fault_code: Optional[str] = None
    size: int = 10
    use_decision: bool = True
    use_semantic: bool = True
    semantic_weight: Optional[float] = None
    vector_k: int = 50
    use_llm: bool = False
    llm_topn: int = 5

@app.post("/opensearch/match")
async def opensearch_match(request: OpenSearchRequest):
    """基于 OpenSearch 的故障现象匹配"""
    if not OPENSEARCH_AVAILABLE:
        return {
            "error": "OpenSearch 不可用",
            "message": "请确保 OpenSearch 服务正常运行并已导入数据"
        }
    
    try:
        if request.use_decision:
            # 使用灰区路由决策，必要时调用 LLM 精选
            result = await opensearch_matcher.match_with_decision_async(
                query=request.q,
                system=request.system,
                part=request.part,
                vehicletype=request.vehicletype,
                fault_code=request.fault_code,
                pass_threshold=settings.pass_threshold,
                gray_low_threshold=settings.gray_low_threshold,
                size=request.size,
                use_semantic=request.use_semantic,
                semantic_weight=request.semantic_weight,
                vector_k=request.vector_k,
                use_llm=request.use_llm,
                llm_picker=closed_set_pick if request.use_llm else None,
                llm_topn=request.llm_topn
            )
        else:
            # 仅返回搜索结果
            result = opensearch_matcher.search_phenomena(
                query=request.q,
                system=request.system,
                part=request.part,
                vehicletype=request.vehicletype,
                fault_code=request.fault_code,
                size=request.size,
                use_semantic=request.use_semantic,
                semantic_weight=request.semantic_weight,
                vector_k=request.vector_k
            )
        
        return result
        
    except Exception as e:
        logger.error(f"OpenSearch 匹配失败: {e}")
        return {
            "error": "OpenSearch 匹配失败",
            "message": str(e),
            "query": request.q,
            "total": 0,
            "top": []
        }

@app.get("/opensearch/stats")
async def opensearch_stats():
    """获取 OpenSearch 索引统计信息"""
    if not OPENSEARCH_AVAILABLE:
        return {"error": "OpenSearch 不可用"}
    
    try:
        return opensearch_matcher.get_statistics()
    except Exception as e:
        logger.error(f"获取 OpenSearch 统计信息失败: {e}")
        return {"error": str(e)}

@app.get("/match/hybrid")
async def hybrid_match(
    q: str = Query(..., description="用户查询"),
    system: Optional[str] = None,
    part: Optional[str] = None,
    vehicletype: Optional[str] = None,
    use_opensearch: bool = Query(True, description="是否使用 OpenSearch"),
    topn_return: int = 3
):
    """混合匹配：结合本地索引和 OpenSearch"""
    query = normalize_query(q)
    
    # 本地匹配结果
    local_result = await match(
        q=q, system=system, part=part, 
        topn_return=topn_return
    )
    
    # OpenSearch 匹配结果
    opensearch_result = None
    if use_opensearch and OPENSEARCH_AVAILABLE:
        try:
            opensearch_result = await opensearch_matcher.match_with_decision_async(
                query=q,
                system=system,
                part=part,
                vehicletype=vehicletype,
                pass_threshold=settings.pass_threshold,
                gray_low_threshold=settings.gray_low_threshold
            )
        except Exception as e:
            logger.error(f"OpenSearch 匹配失败: {e}")
    
    return {
        "query": query,
        "local_result": local_result,
        "opensearch_result": opensearch_result,
        "recommendation": {
            "use_local": local_result.decision["mode"] == "direct",
            "use_opensearch": (
                opensearch_result and 
                opensearch_result.get("decision", {}).get("mode") == "direct"
            ),
            "confidence_comparison": {
                "local": local_result.decision.get("confidence", 0.0),
                "opensearch": (
                    opensearch_result.get("decision", {}).get("confidence", 0.0)
                    if opensearch_result else 0.0
                )
            }
        }
    }

static_dir = os.path.join(os.path.dirname(__file__), "..", "web")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")

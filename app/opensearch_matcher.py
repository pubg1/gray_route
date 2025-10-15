#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于 OpenSearch 的故障现象匹配服务
按照 README.md 设计，从 OpenSearch 中查询匹配故障现象
"""

import os
import sys
import math
import logging
from typing import List, Dict, Optional, Tuple, Callable, Awaitable, Any
from opensearchpy import OpenSearch

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG

try:
    from app.embedding import get_embedder  # type: ignore
except Exception:  # pragma: no cover - 仅在模型不可用时触发
    get_embedder = None

logger = logging.getLogger(__name__)

class OpenSearchMatcher:
    """基于 OpenSearch 的故障现象匹配器"""
    
    def __init__(self):
        """初始化 OpenSearch 连接"""
        try:
            self.client = OpenSearch(
                hosts=[{
                    'host': OPENSEARCH_CONFIG['host'].replace('https://', '').replace('http://', ''),
                    'port': OPENSEARCH_CONFIG['port']
                }],
                http_auth=(OPENSEARCH_CONFIG['username'], OPENSEARCH_CONFIG['password']),
                use_ssl=OPENSEARCH_CONFIG['use_ssl'],
                verify_certs=OPENSEARCH_CONFIG['verify_certs'],
                ssl_assert_hostname=OPENSEARCH_CONFIG.get('ssl_assert_hostname', False),
                ssl_show_warn=OPENSEARCH_CONFIG.get('ssl_show_warn', False),
                timeout=OPENSEARCH_CONFIG.get('timeout', 30)
            )
            
            # 测试连接
            info = self.client.info()
            logger.info(f"OpenSearch 连接成功: {info['version']['number']}")
            
        except Exception as e:
            logger.error(f"OpenSearch 连接失败: {e}")
            raise

        self.vector_field = INDEX_CONFIG.get('vector_field', 'text_vector')
        self.vector_num_candidates = INDEX_CONFIG.get('vector_num_candidates', 200)
        self.default_semantic_weight = INDEX_CONFIG.get('default_semantic_weight', 0.6)

        self.embedder = None
        self.semantic_available = False
        if get_embedder is not None:
            try:
                self.embedder = get_embedder()
                self.semantic_available = True
                logger.info("语义检索已启用: 成功加载向量模型")
            except Exception as embed_err:  # pragma: no cover - 模型加载失败较难复现
                logger.warning(f"加载语义向量模型失败，已自动关闭语义检索: {embed_err}")
        else:
            logger.warning("未找到向量模型加载函数，语义检索不可用")

    @staticmethod
    def _build_filters(system: Optional[str],
                       part: Optional[str],
                       vehicletype: Optional[str],
                       fault_code: Optional[str]) -> List[Dict]:
        filters: List[Dict] = []
        if system:
            filters.append({"term": {"system.keyword": system}})
        if part:
            filters.append({"match": {"part": part}})
        if vehicletype:
            filters.append({"term": {"vehicletype.keyword": vehicletype}})
        if fault_code:
            filters.append({"match": {"spare4": fault_code}})
        return filters

    def _encode_query(self, query: str) -> Optional[List[float]]:
        if not self.embedder:
            return None
        try:
            vec = self.embedder.encode([query])[0]
            return vec.tolist()
        except Exception as e:  # pragma: no cover - 推理异常
            logger.error(f"生成查询向量失败: {e}")
            return None

    @staticmethod
    def _extract_source(hit: Dict) -> Tuple[str, Dict]:
        source = hit.get('_source', {}) or {}
        doc_id = hit.get('_id') or source.get('id', '')
        return doc_id, source


    def search_phenomena(self,
                        query: str,
                        system: Optional[str] = None,
                        part: Optional[str] = None,
                        vehicletype: Optional[str] = None,
                        fault_code: Optional[str] = None,
                        size: int = 10,
                        use_semantic: bool = True,
                        semantic_weight: Optional[float] = None,
                        vector_k: int = 50) -> Dict:
        """搜索故障现象并支持语义向量融合"""

        try:
            filters = self._build_filters(system, part, vehicletype, fault_code)

            search_body = {
                "query": {
                    "bool": {
                        "must": {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "text^3.0",
                                    "symptoms^2.8",
                                    "topic^2.5",
                                    "discussion^2.5",
                                    "spare2^2.3",
                                    "spare4^2.2",
                                    "searchContent^2.0",
                                    "search_content^2.0",
                                    "part^2.0",
                                    "spare1^1.8",
                                    "spare15^1.8",
                                    "egon^1.5",
                                    "vehicletype^1.5",
                                    "vehiclebrand^1.3",
                                    "search^1.0",
                                    "solution^1.0",
                                    "faultcode^0.8"
                                ],
                                "type": "best_fields",
                                "fuzziness": "AUTO",
                                "minimum_should_match": "75%"
                            }
                        },
                        "filter": filters,
                        "should": [
                            {
                                "range": {
                                    "popularity": {"gte": 50}
                                }
                            }
                        ]
                    }
                },
                "size": size,
                "highlight": {
                    "fields": {
                        "text": {
                            "fragment_size": 150,
                            "number_of_fragments": 1,
                            "pre_tags": ["<mark>"],
                            "post_tags": ["</mark>"]
                        },
                        "discussion": {
                            "fragment_size": 100,
                            "number_of_fragments": 1,
                            "pre_tags": ["<mark>"],
                            "post_tags": ["</mark>"]
                        }
                    }
                },
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"popularity": {"order": "desc"}},
                    {"searchNum": {"order": "desc"}}
                ]
            }

            response = self.client.search(
                index=INDEX_CONFIG['name'],
                body=search_body,
                size=size
            )

            merged: Dict[str, Dict] = {}
            for hit in response['hits']['hits']:
                doc_id, source = self._extract_source(hit)
                bm25_raw = float(hit.get('_score') or 0.0)
                merged[doc_id] = {
                    "id": doc_id,
                    "text": source.get('text', ''),
                    "system": source.get('system', ''),
                    "part": source.get('part', ''),
                    "tags": source.get('tags', []),
                    "vehicletype": source.get('vehicletype', ''),
                    "vehiclebrand": source.get('vehiclebrand', ''),
                    "topic": source.get('topic', ''),
                    "symptoms": source.get('symptoms', ''),
                    "discussion": source.get('discussion', ''),
                    "solution": source.get('solution', ''),
                    "egon": source.get('egon', ''),
                    "spare1": source.get('spare1', ''),
                    "spare2": source.get('spare2', ''),
                    "spare4": source.get('spare4', ''),
                    "spare15": source.get('spare15', ''),
                    "faultcode": source.get('faultcode', ''),
                    "createtime": source.get('createtime', ''),
                    "money": source.get('money', ''),
                    "popularity": source.get('popularity', 0),
                    "searchNum": source.get('searchNum', 0),
                    "rate": source.get('rate'),
                    "highlight": hit.get('highlight', {}),
                    "sources": ["keyword"],
                    "bm25_score": min(1.0, bm25_raw / 10.0),
                    "semantic_score": 0.0,
                    "cosine": 0.0,
                    "rerank_score": 0.0
                }

            effective_semantic = bool(use_semantic and self.semantic_available)
            semantic_weight = self.default_semantic_weight if semantic_weight is None else float(semantic_weight)
            semantic_weight = min(max(semantic_weight, 0.0), 1.0)

            try:
                vector_k = max(1, int(vector_k))
            except (TypeError, ValueError):
                vector_k = max(1, size)

            if effective_semantic and self.vector_field:
                query_vector = self._encode_query(query)
                if query_vector is not None:
                    knn_body = {
                        "size": vector_k,
                        "query": {
                            "bool": {
                                "filter": filters
                            }
                        },
                        "knn": {
                            "field": self.vector_field,
                            "query_vector": query_vector,
                            "k": vector_k,
                            "num_candidates": max(vector_k * 4, self.vector_num_candidates)
                        }
                    }
                    try:
                        knn_resp = self.client.search(
                            index=INDEX_CONFIG['name'],
                            body=knn_body
                        )
                        for hit in knn_resp['hits']['hits']:
                            doc_id, source = self._extract_source(hit)
                            semantic_raw = float(hit.get('_score') or 0.0)
                            item = merged.get(doc_id)
                            if not item:
                                item = {
                                    "id": doc_id,
                                    "text": source.get('text', ''),
                                    "system": source.get('system', ''),
                                    "part": source.get('part', ''),
                                    "tags": source.get('tags', []),
                                    "vehicletype": source.get('vehicletype', ''),
                                    "vehiclebrand": source.get('vehiclebrand', ''),
                                    "topic": source.get('topic', ''),
                                    "symptoms": source.get('symptoms', ''),
                                    "discussion": source.get('discussion', ''),
                                    "solution": source.get('solution', ''),
                                    "egon": source.get('egon', ''),
                                    "spare1": source.get('spare1', ''),
                                    "spare2": source.get('spare2', ''),
                                    "spare4": source.get('spare4', ''),
                                    "spare15": source.get('spare15', ''),
                                    "faultcode": source.get('faultcode', ''),
                                    "createtime": source.get('createtime', ''),
                                    "money": source.get('money', ''),
                                    "popularity": source.get('popularity', 0),
                                    "searchNum": source.get('searchNum', 0),
                                    "rate": source.get('rate'),
                                    "highlight": hit.get('highlight', {}),
                                    "sources": [],
                                    "bm25_score": 0.0,
                                    "semantic_score": 0.0,
                                    "cosine": 0.0,
                                    "rerank_score": 0.0
                                }
                                merged[doc_id] = item
                            item['semantic_score'] = max(item.get('semantic_score', 0.0), semantic_raw)
                            cosine_norm = (semantic_raw + 1.0) / 2.0
                            cosine_norm = min(1.0, max(0.0, cosine_norm))
                            item['cosine'] = max(item.get('cosine', 0.0), cosine_norm)
                            sources = set(item.get('sources', []))
                            sources.add('semantic')
                            item['sources'] = list(sources)
                            if not item.get('highlight'):
                                item['highlight'] = hit.get('highlight', {})
                    except Exception as knn_err:
                        logger.error(f"语义检索失败: {knn_err}")
                        effective_semantic = False

            results: List[Dict] = []
            for item in merged.values():
                bm25_norm = float(item.get('bm25_score') or 0.0)
                semantic_norm = float(item.get('cosine') or 0.0) if effective_semantic else 0.0
                popularity = item.get('popularity', 0) or 0
                popularity_norm = min(1.0, math.log1p(popularity) / 5.0)
                search_num = item.get('searchNum', 0) or 0
                search_norm = min(1.0, search_num / 50.0)

                fusion_base = semantic_weight * semantic_norm + (1.0 - semantic_weight) * bm25_norm
                final_score = min(1.0, fusion_base + 0.05 * popularity_norm + 0.05 * search_norm)

                why: List[str] = []
                if semantic_norm >= 0.6:
                    why.append("语义近")
                elif semantic_norm >= 0.4:
                    why.append("语义相关")
                if bm25_norm >= 0.2:
                    why.append("关键词命中")
                if system and item.get('system') == system:
                    why.append("系统一致")
                if part and item.get('part') and part in item.get('part'):
                    why.append("部件相近")
                if popularity > 100:
                    why.append("热门案例")
                elif popularity > 50:
                    why.append("常见问题")

                item['final_score'] = final_score
                item['rerank_score'] = fusion_base
                item['bm25_score'] = bm25_norm
                item['cosine'] = semantic_norm
                item['why'] = why or ["文本匹配"]
                item['sources'] = sorted(set(item.get('sources', [])))

                results.append(item)

            results.sort(key=lambda x: x.get('final_score', 0.0), reverse=True)

            metadata = {
                "semantic_used": effective_semantic,
                "semantic_weight": semantic_weight if effective_semantic else 0.0,
                "vector_k": vector_k if effective_semantic else 0,
                "keyword_size": size
            }

            return {
                "query": query,
                "total": response['hits']['total']['value'],
                "top": results[:size],
                "metadata": metadata
            }
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return {
                "query": query,
                "total": 0,
                "top": [],
                "error": str(e)
            }
    def _generate_base_decision(
        self,
        search_result: Dict,
        pass_threshold: float,
        gray_low_threshold: float
    ) -> Tuple[Dict, Dict[str, Any]]:
        """根据搜索结果生成基础决策，并返回上下文信息"""

        top_results: List[Dict] = search_result.get("top", []) or []
        metadata = search_result.get("metadata", {}) or {}

        context: Dict[str, Any] = {
            "top": top_results,
            "metadata": metadata,
            "pass_threshold": pass_threshold,
            "gray_low_threshold": gray_low_threshold,
            "best_match": top_results[0] if top_results else None,
            "best_score": float(top_results[0].get("final_score", 0.0)) if top_results else 0.0,
            "semantic_used": bool(metadata.get("semantic_used", False))
        }

        if not top_results:
            decision = {
                "mode": "no_match",
                "chosen_id": None,
                "confidence": 0.0,
                "reason": "无匹配结果"
            }
            return decision, context

        best_match: Dict = context["best_match"]
        best_score: float = context["best_score"]
        semantic_used: bool = context["semantic_used"]

        if best_score >= pass_threshold:
            reason = f"高置信度匹配 (score: {best_score:.3f})"
            if semantic_used:
                reason += "，融合语义检索"
            decision = {
                "mode": "direct",
                "chosen_id": best_match["id"],
                "confidence": best_score,
                "reason": reason
            }
            return decision, context

        if best_score >= gray_low_threshold:
            decision = {
                "mode": "gray",
                "chosen_id": best_match["id"],
                "confidence": best_score,
                "reason": f"灰区匹配，建议人工确认 (score: {best_score:.3f})",
                "alternatives": [
                    {
                        "id": result.get("id"),
                        "text": (result.get("text", "") or "")[:100] + "...",
                        "score": result.get("final_score")
                    }
                    for result in top_results[1:4]
                ]
            }
            if semantic_used:
                decision["reason"] += "，含语义召回"
            return decision, context

        decision = {
            "mode": "reject",
            "chosen_id": None,
            "confidence": best_score,
            "reason": f"置信度过低 (score: {best_score:.3f})",
            "suggestions": [
                (result.get("text", "") or "")[:50] + "..."
                for result in top_results[:3]
            ]
        }
        return decision, context

    def match_with_decision(self,
                           query: str,
                           system: Optional[str] = None,
                           part: Optional[str] = None,
                           vehicletype: Optional[str] = None,
                           fault_code: Optional[str] = None,
                           pass_threshold: float = 0.84,
                           gray_low_threshold: float = 0.65,
                           size: int = 10,
                           use_semantic: bool = True,
                           semantic_weight: Optional[float] = None,
                           vector_k: int = 50) -> Dict:
        """按照 README.md 设计进行故障现象匹配，包含灰区路由决策"""

        search_result = self.search_phenomena(
            query=query,
            system=system,
            part=part,
            vehicletype=vehicletype,
            fault_code=fault_code,
            size=size,
            use_semantic=use_semantic,
            semantic_weight=semantic_weight,
            vector_k=vector_k
        )

        decision, _ = self._generate_base_decision(
            search_result,
            pass_threshold=pass_threshold,
            gray_low_threshold=gray_low_threshold
        )

        return {
            **search_result,
            "decision": decision
        }

    async def match_with_decision_async(
        self,
        query: str,
        system: Optional[str] = None,
        part: Optional[str] = None,
        vehicletype: Optional[str] = None,
        fault_code: Optional[str] = None,
        pass_threshold: float = 0.84,
        gray_low_threshold: float = 0.65,
        size: int = 10,
        use_semantic: bool = True,
        semantic_weight: Optional[float] = None,
        vector_k: int = 50,
        use_llm: bool = False,
        llm_picker: Optional[Callable[[str, List[Dict[str, str]]], Awaitable[Dict[str, Any]]]] = None,
        llm_topn: int = 5
    ) -> Dict:
        """支持异步 LLM 精选的匹配流程"""

        search_result = self.search_phenomena(
            query=query,
            system=system,
            part=part,
            vehicletype=vehicletype,
            fault_code=fault_code,
            size=size,
            use_semantic=use_semantic,
            semantic_weight=semantic_weight,
            vector_k=vector_k
        )

        decision, context = self._generate_base_decision(
            search_result,
            pass_threshold=pass_threshold,
            gray_low_threshold=gray_low_threshold
        )

        metadata = search_result.setdefault("metadata", {})
        metadata.setdefault("llm_used", False)

        best_match = context.get("best_match")
        best_score = float(context.get("best_score", 0.0) or 0.0)

        should_try_llm = (
            use_llm
            and llm_picker is not None
            and best_match is not None
            and gray_low_threshold <= best_score < pass_threshold
        )

        if should_try_llm:
            try:
                llm_topn = max(1, int(llm_topn))
            except (TypeError, ValueError):
                llm_topn = 5

            candidates = []
            for item in context.get("top", [])[:llm_topn]:
                candidates.append({
                    "id": str(item.get("id", "")),
                    "text": (item.get("text", "") or "")[:300]
                })

            metadata["llm_used"] = True
            metadata["llm_candidate_count"] = len(candidates)

            try:
                llm_response = await llm_picker(query, candidates)
            except Exception as llm_err:  # pragma: no cover - 网络/配置错误较难复现
                logger.error(f"LLM 精选失败: {llm_err}")
                llm_response = {"chosen_id": "UNKNOWN", "confidence": 0.0, "why": "llm_error"}

            metadata["llm_response"] = llm_response

            chosen_id = llm_response.get("chosen_id")
            llm_conf = float(llm_response.get("confidence") or 0.0)

            if chosen_id and chosen_id != "UNKNOWN":
                chosen_item = next(
                    (item for item in context.get("top", []) if str(item.get("id")) == str(chosen_id)),
                    best_match
                )
                base_score = float(chosen_item.get("final_score") or 0.0)
                confidence = max(base_score, llm_conf, best_score)
                decision = {
                    "mode": "llm",
                    "chosen_id": chosen_item.get("id"),
                    "confidence": confidence,
                    "reason": llm_response.get("why") or "LLM 精选候选",
                    "llm": {
                        "confidence": llm_conf,
                        "why": llm_response.get("why"),
                        "chosen_id": chosen_id
                    },
                    "alternatives": [
                        {
                            "id": item.get("id"),
                            "text": (item.get("text", "") or "")[:100] + "...",
                            "score": item.get("final_score")
                        }
                        for item in context.get("top", [])
                        if item.get("id") != chosen_item.get("id")
                    ][:3]
                }
            else:
                decision = {
                    **decision,
                    "llm": {
                        "confidence": llm_conf,
                        "why": llm_response.get("why"),
                        "chosen_id": chosen_id or "UNKNOWN"
                    }
                }

        return {
            **search_result,
            "decision": decision
        }
    def get_statistics(self) -> Dict:
        """获取索引统计信息"""
        try:
            # 获取索引统计
            stats = self.client.indices.stats(index=INDEX_CONFIG['name'])
            index_stats = stats['indices'][INDEX_CONFIG['name']]
            
            # 获取系统分布
            agg_body = {
                "size": 0,
                "aggs": {
                    "systems": {
                        "terms": {"field": "system.keyword", "size": 20}
                    },
                    "vehicletypes": {
                        "terms": {"field": "vehicletype.keyword", "size": 20}
                    },
                    "popularity_stats": {
                        "stats": {"field": "popularity"}
                    }
                }
            }
            
            agg_response = self.client.search(
                index=INDEX_CONFIG['name'], 
                body=agg_body
            )
            
            return {
                "total_documents": index_stats['total']['docs']['count'],
                "index_size_mb": index_stats['total']['store']['size_in_bytes'] / (1024 * 1024),
                "systems": [
                    {"name": bucket["key"], "count": bucket["doc_count"]}
                    for bucket in agg_response['aggregations']['systems']['buckets']
                ],
                "vehicletypes": [
                    {"name": bucket["key"], "count": bucket["doc_count"]}
                    for bucket in agg_response['aggregations']['vehicletypes']['buckets']
                ],
                "popularity_stats": agg_response['aggregations']['popularity_stats']
            }
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {"error": str(e)}

# 创建全局实例
try:
    opensearch_matcher = OpenSearchMatcher()
except Exception as e:
    logger.error(f"初始化 OpenSearch 匹配器失败: {e}")
    opensearch_matcher = None

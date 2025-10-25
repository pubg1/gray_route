#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于 OpenSearch 的故障现象匹配服务
按照 README.md 设计，从 OpenSearch 中查询匹配故障现象
"""

import math
import os
import re
import sys
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

from opensearchpy import OpenSearch

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG
from .utils.calibration import clamp, compute_stats, logistic_from_stats

try:
    from app.embedding import get_embedder  # type: ignore
except Exception:  # pragma: no cover - 仅在模型不可用时触发
    get_embedder = None

logger = logging.getLogger(__name__)


PHENOMENA_MULTI_MATCH_FIELDS: List[str] = [
    "text^3.0",
    "symptoms^3.0",
    "symptom^3.0",
    "fault_symptom^3.0",
    "faultSymptom^3.0",
    "symptom_desc^2.8",
    "symptomDesc^2.8",
    "topic^2.5",
    "summary^2.3",
    "discussion^2.5",
    "fault_point^2.5",
    "faultPoint^2.5",
    "analysis^2.0",
    "search_content^2.0",
    "searchContent^2.0",
    "search^1.8",
    "solution^1.8",
    "part^1.5",
    "component^1.5",
    "system^1.5",
    "system_name^1.3",
    "vehicletype^1.5",
    "vehicle_model^1.5",
    "vehicle_name^1.3",
    "vehiclename^1.3",
    "vehiclebrand^1.3",
    "vehicle_brand^1.3",
    "brand^1.3",
    "spare2^1.0",
    "spare4^1.0",
    "faultcode^0.8",
    "fault_code^0.8",
    "dtc^0.8",
]

FAULT_POINT_TEXT_FIELDS: List[str] = [
    "discussion^3.0",
    "fault_point^3.0",
    "faultPoint^3.0",
    "symptoms^2.5",
    "fault_symptom^2.5",
    "symptom^2.0",
    "text^2.0",
    "topic^1.5",
    "summary^1.5",
    "solution^1.2",
]

VEHICLE_NAME_FIELDS: List[str] = [
    "vehicletype^2.0",
    "vehicle_model^2.0",
    "vehicle_name^1.8",
    "vehiclename^1.8",
    "topic^1.5",
    "symptoms",
    "searchContent",
    "search_content",
    "search",
]

CONTROL_UNIT_FIELDS: List[str] = [
    "part^2.0",
    "component^2.0",
    "component_name^2.0",
    "control_unit^2.0",
    "system^1.5",
    "discussion^1.2",
    "fault_point^1.2",
    "spare2",
    "spare1",
]

FAULT_CODE_FIELDS: List[str] = [
    "faultcode",
    "fault_code",
    "dtc",
    "dtc_code",
    "spare4",
]

MODEL_YEAR_FIELDS: List[str] = [
    "modelyear",
    "model_year",
    "year",
    "spare1",
    "spare15",
    "vehicletype",
]


def _pick_first(source: Dict[str, Any], keys: Sequence[str], *, default: Any = None) -> Any:
    for key in keys:
        if not key:
            continue
        value = source.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
            continue
        if isinstance(value, list):
            if value:
                return value
            continue
        if isinstance(value, dict):
            if value:
                return value
            continue
        return value
    return default


def _normalize_tags(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        parts = re.split(r"[,，;；\s]+", value)
        return [part.strip() for part in parts if part.strip()]
    return [str(value).strip()] if str(value).strip() else []


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        text = str(value).strip()
        if not text:
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        text = str(value).strip()
        if not text:
            return default
        return int(float(text))
    except (TypeError, ValueError):
        return default


def _extract_common_fields(source: Dict[str, Any]) -> Dict[str, Any]:
    brand = _pick_first(source, ["vehiclebrand", "vehicle_brand", "brand", "car_brand"], default="") or ""
    vehicletype = _pick_first(source, ["vehicletype", "vehicle_model", "vehicle_name", "vehiclename", "model", "series", "car_model"], default="") or ""
    modelyear = _pick_first(source, ["modelyear", "model_year", "year", "spare1"], default="") or ""
    search_content = _pick_first(source, ["searchContent", "search_content", "search"], default="") or ""

    fields: Dict[str, Any] = {
        "text": _pick_first(source, [
            "text",
            "fault_symptom",
            "symptoms",
            "symptom",
            "summary",
            "fault_description",
            "fault_desc",
            "discussion",
            "fault_point",
        ], default="") or "",
        "system": _pick_first(source, ["system", "system_name", "systemCategory", "system_category"], default="") or "",
        "part": _pick_first(source, ["part", "component", "component_name", "control_unit", "fault_part"], default="") or "",
        "tags": _normalize_tags(_pick_first(source, ["tags", "labels", "tag_list"], default=[])),
        "vehicletype": vehicletype,
        "vehiclebrand": brand,
        "topic": _pick_first(source, ["topic", "category", "fault_category", "fault_type"], default="") or "",
        "symptoms": _pick_first(source, ["symptoms", "fault_symptom", "symptom", "text"], default="") or "",
        "discussion": _pick_first(source, ["discussion", "fault_point", "fault_location", "faultDescription", "analysis"], default="") or "",
        "solution": _pick_first(source, ["solution", "repair_solution", "measure", "fix"], default="") or "",
        "egon": source.get('egon', ''),
        "spare1": modelyear,
        "spare2": _pick_first(source, ["spare2", "component", "component_name", "control_unit"], default="") or "",
        "spare4": _pick_first(source, ["spare4", "faultcode", "fault_code", "dtc", "code"], default="") or "",
        "spare15": _pick_first(source, ["spare15", "series", "subseries"], default="") or "",
        "faultcode": _pick_first(source, ["faultcode", "fault_code", "dtc", "code", "spare4"], default="") or "",
        "createtime": source.get('createtime', ''),
        "money": source.get('money', ''),
        "popularity": _coerce_float(_pick_first(source, ["popularity", "popularity_score"], default=0.0)),
        "searchNum": _coerce_int(_pick_first(source, ["searchNum", "search_num"], default=0)),
        "rate": source.get('rate'),
        "modelyear": modelyear,
        "searchContent": search_content,
        "search_content": search_content,
        "brand": brand,
        "vehicle_brand": brand,
        "vehicle_model": vehicletype,
    }

    return fields


def _select_highlight(highlight: Dict[str, List[str]], keys: Sequence[str]) -> Optional[str]:
    for key in keys:
        fragments = highlight.get(key)
        if fragments:
            return fragments[0]
    return None


def _parse_version_number(version: str) -> Tuple[int, ...]:
    """将 OpenSearch 版本号解析为整数元组，便于比较。"""

    if not version:
        return tuple()
    numeric_part = version.split("-")[0]
    parts = [part for part in re.split(r"[^0-9]+", numeric_part) if part]
    if not parts:
        return tuple()
    try:
        return tuple(int(part) for part in parts)
    except ValueError:
        return tuple()

class OpenSearchMatcher:
    """基于 OpenSearch 的故障现象匹配器"""
    
    def __init__(self):
        """初始化 OpenSearch 连接"""
        self.server_version = ''
        version_tuple: Tuple[int, ...] = tuple()
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
            self.server_version = str(info.get('version', {}).get('number', ''))
            version_tuple = _parse_version_number(self.server_version)
            logger.info(f"OpenSearch 连接成功: {self.server_version}")
            
        except Exception as e:
            logger.error(f"OpenSearch 连接失败: {e}")
            raise

        self.vector_field = INDEX_CONFIG.get('vector_field', 'text_vector')
        self.vector_num_candidates = INDEX_CONFIG.get('vector_num_candidates', 200)
        self.default_semantic_weight = INDEX_CONFIG.get('default_semantic_weight', 0.6)

        self.embedder = None
        self.semantic_available = False
        self._knn_query_style = 'top_level'
        version_major_minor = version_tuple[:2] if version_tuple else tuple()
        if version_major_minor and version_major_minor < (2, 9):
            self._knn_query_style = 'nested'
            logger.info(
                "检测到 OpenSearch 版本 %s 不支持顶层 kNN 查询，默认使用 bool.must 语法",
                self.server_version
            )
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
            system_should: List[Dict[str, Any]] = [
                {"term": {"system.keyword": system}},
                {"term": {"system_name.keyword": system}},
                {"match_phrase": {"system": system}},
                {"match_phrase": {"system_name": system}},
            ]
            filters.append({
                "bool": {
                    "should": system_should,
                    "minimum_should_match": 1,
                }
            })
        if part:
            filters.append({
                "multi_match": {
                    "query": part,
                    "fields": [
                        "part^2.0",
                        "component^2.0",
                        "component_name^2.0",
                        "control_unit^1.5",
                        "fault_point^1.2",
                    ],
                    "type": "best_fields",
                }
            })
        if vehicletype:
            filters.append({
                "multi_match": {
                    "query": vehicletype,
                    "fields": [
                        "vehicletype^2.0",
                        "vehicle_model^2.0",
                        "vehicle_name^1.5",
                        "vehiclename^1.5",
                        "model^1.2",
                        "series^1.2",
                    ],
                    "type": "best_fields",
                }
            })
        if fault_code:
            should: List[Dict[str, Any]] = [
                {"match_phrase": {field: fault_code}}
                for field in FAULT_CODE_FIELDS
            ]
            filters.append({
                "bool": {
                    "should": should,
                    "minimum_should_match": 1,
                }
            })
        return filters

    def _build_knn_body(self,
                        query_vector: Sequence[float],
                        vector_k: int,
                        filters: Sequence[Dict]) -> Dict[str, Any]:
        filter_clauses = list(filters or [])
        bool_query: Dict[str, Any] = {}
        if filter_clauses:
            bool_query["filter"] = filter_clauses

        num_candidates = max(vector_k * 4, self.vector_num_candidates)

        if self._knn_query_style == 'nested':
            knn_clause = {
                "knn": {
                    self.vector_field: {
                        "vector": list(query_vector),
                        "k": vector_k,
                        "num_candidates": num_candidates,
                    }
                }
            }
            bool_query.setdefault("must", [])
            bool_query["must"].append(knn_clause)
            return {
                "size": vector_k,
                "query": {
                    "bool": bool_query
                }
            }

        return {
            "size": vector_k,
            "query": {
                "bool": bool_query
            },
            "knn": {
                "field": self.vector_field,
                "query_vector": list(query_vector),
                "k": vector_k,
                "num_candidates": num_candidates
            }
        }

    @staticmethod
    def _should_use_nested_knn(error: Exception) -> bool:
        message = str(error)
        keywords = [
            "Unknown key for a START_OBJECT in [knn]",
            "Unknown key for a FIELD_NAME in [knn]",
            "Failed to parse [knn]",
            "parsing_exception",
        ]
        return any(keyword in message for keyword in keywords)

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
                                "fields": PHENOMENA_MULTI_MATCH_FIELDS,
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
                            },
                            {
                                "range": {
                                    "popularity_score": {"gte": 50}
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
                        "symptoms": {
                            "fragment_size": 150,
                            "number_of_fragments": 1,
                            "pre_tags": ["<mark>"],
                            "post_tags": ["</mark>"]
                        },
                        "fault_symptom": {
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
                        },
                        "fault_point": {
                            "fragment_size": 100,
                            "number_of_fragments": 1,
                            "pre_tags": ["<mark>"],
                            "post_tags": ["</mark>"]
                        }
                    }
                },
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"popularity": {"order": "desc", "missing": "_last", "unmapped_type": "float"}},
                    {"search_num": {"order": "desc", "missing": "_last", "unmapped_type": "integer"}},
                    {"searchNum": {"order": "desc", "missing": "_last", "unmapped_type": "integer"}}
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
                fields = _extract_common_fields(source)
                merged[doc_id] = {
                    "id": doc_id,
                    **fields,
                    "highlight": hit.get('highlight', {}) or {},
                    "sources": ["keyword"],
                    "bm25_raw": bm25_raw,
                    "semantic_raw": 0.0,
                    "bm25_score": 0.0,
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
                    knn_body = self._build_knn_body(query_vector, vector_k, filters)
                    try:
                        knn_resp = self.client.search(
                            index=INDEX_CONFIG['name'],
                            body=knn_body
                        )
                    except Exception as knn_err:
                        if (
                            self._knn_query_style == 'top_level'
                            and self._should_use_nested_knn(knn_err)
                        ):
                            logger.warning(
                                "顶层 kNN 查询失败，自动回退到 bool.must 语法: %s",
                                knn_err
                            )
                            self._knn_query_style = 'nested'
                            knn_body = self._build_knn_body(query_vector, vector_k, filters)
                            try:
                                knn_resp = self.client.search(
                                    index=INDEX_CONFIG['name'],
                                    body=knn_body
                                )
                            except Exception as nested_err:
                                logger.error(f"语义检索失败: {nested_err}")
                                effective_semantic = False
                                knn_resp = None
                        else:
                            logger.error(f"语义检索失败: {knn_err}")
                            effective_semantic = False
                            knn_resp = None
                    if knn_resp:
                        for hit in knn_resp['hits']['hits']:
                            doc_id, source = self._extract_source(hit)
                            semantic_raw = float(hit.get('_score') or 0.0)
                            item = merged.get(doc_id)
                            if not item:
                                fields = _extract_common_fields(source)
                                item = {
                                    "id": doc_id,
                                    **fields,
                                    "highlight": hit.get('highlight', {}) or {},
                                    "sources": [],
                                    "bm25_raw": 0.0,
                                    "semantic_raw": 0.0,
                                    "bm25_score": 0.0,
                                    "semantic_score": 0.0,
                                    "cosine": 0.0,
                                    "rerank_score": 0.0
                                }
                                merged[doc_id] = item
                            item['semantic_raw'] = max(item.get('semantic_raw', 0.0), semantic_raw)
                            cosine_norm = (semantic_raw + 1.0) / 2.0
                            cosine_norm = min(1.0, max(0.0, cosine_norm))
                            item['cosine'] = max(item.get('cosine', 0.0), cosine_norm)
                            sources = set(item.get('sources', []))
                            sources.add('semantic')
                            item['sources'] = list(sources)
                            if not item.get('highlight'):
                                item['highlight'] = hit.get('highlight', {})

            bm25_stats = compute_stats(
                item.get('bm25_raw')
                for item in merged.values()
                if item.get('bm25_raw') is not None
            )
            semantic_stats = compute_stats(
                item.get('semantic_raw')
                for item in merged.values()
                if item.get('semantic_raw') is not None
            )

            results: List[Dict] = []
            for item in merged.values():
                bm25_raw = float(item.get('bm25_raw') or 0.0)
                semantic_raw = float(item.get('semantic_raw') or 0.0)

                bm25_norm = logistic_from_stats(
                    bm25_raw,
                    bm25_stats,
                    fallback=clamp(bm25_raw / 10.0),
                )
                semantic_norm = 0.0
                if effective_semantic:
                    semantic_norm = logistic_from_stats(
                        semantic_raw,
                        semantic_stats,
                        fallback=clamp((semantic_raw + 1.0) / 2.0),
                    )
                popularity_val = _coerce_float(item.get('popularity', 0))
                item['popularity'] = popularity_val
                popularity_norm = clamp(math.log1p(max(0.0, popularity_val)) / 5.0)
                search_num_val = max(0, _coerce_int(item.get('searchNum', 0)))
                item['searchNum'] = search_num_val
                search_norm = clamp(float(search_num_val) / 50.0)

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
                if popularity_val > 100:
                    why.append("热门案例")
                elif popularity_val > 50:
                    why.append("常见问题")

                item['final_score'] = final_score
                item['rerank_score'] = fusion_base
                item['bm25_score'] = bm25_norm
                item['semantic_score'] = semantic_norm
                item['cosine'] = semantic_norm
                item['why'] = why or ["文本匹配"]
                item['sources'] = sorted(set(item.get('sources', [])))

                results.append(item)

            results.sort(key=lambda x: x.get('final_score', 0.0), reverse=True)

            metadata = {
                "semantic_used": effective_semantic,
                "semantic_weight": semantic_weight if effective_semantic else 0.0,
                "vector_k": vector_k if effective_semantic else 0,
                "keyword_size": size,
                "bm25_stats": {
                    "mean": bm25_stats[0],
                    "std": bm25_stats[1],
                } if bm25_stats else None,
                "semantic_stats": {
                    "mean": semantic_stats[0],
                    "std": semantic_stats[1],
                } if semantic_stats else None,
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

    def search_fault_points(
        self,
        vehicle_brand: Optional[str] = None,
        vehicle_name: Optional[str] = None,
        model_year: Optional[str] = None,
        fault_code: Optional[str] = None,
        control_unit: Optional[str] = None,
        symptom: Optional[str] = None,
        size: int = 5,
    ) -> Dict:
        """根据车辆信息和故障现象，检索 discussion 字段中的故障点说明"""

        try:
            must_clauses: List[Dict[str, Any]] = []
            should_clauses: List[Dict[str, Any]] = []

            if vehicle_brand:
                must_clauses.append({
                    "multi_match": {
                        "query": vehicle_brand,
                        "fields": [
                            "vehiclebrand^2.0",
                            "vehicle_brand^2.0",
                            "brand^1.8",
                        ],
                        "type": "best_fields",
                    }
                })

            if vehicle_name:
                must_clauses.append({
                    "multi_match": {
                        "query": vehicle_name,
                        "fields": VEHICLE_NAME_FIELDS,
                        "type": "best_fields",
                    }
                })

            if model_year:
                year_should = [
                    {"match_phrase": {field: model_year}}
                    for field in MODEL_YEAR_FIELDS
                ]
                must_clauses.append({
                    "bool": {
                        "should": year_should,
                        "minimum_should_match": 1,
                    }
                })

            if control_unit:
                must_clauses.append({
                    "multi_match": {
                        "query": control_unit,
                        "fields": CONTROL_UNIT_FIELDS,
                        "type": "best_fields",
                    }
                })

            if symptom:
                must_clauses.append({
                    "multi_match": {
                        "query": symptom,
                        "fields": FAULT_POINT_TEXT_FIELDS,
                        "type": "best_fields",
                        "fuzziness": "AUTO",
                        "minimum_should_match": "70%",
                    }
                })

            if fault_code:
                should_clauses.extend(
                    {"match_phrase": {field: fault_code}}
                    for field in FAULT_CODE_FIELDS
                )

            if not must_clauses:
                must_clauses.append({"match_all": {}})

            bool_query: Dict[str, Any] = {
                "must": must_clauses,
            }
            if should_clauses:
                bool_query["should"] = should_clauses
                bool_query["minimum_should_match"] = 1

            search_body: Dict[str, Any] = {
                "query": {"bool": bool_query},
                "size": max(1, size),
                "highlight": {
                    "fields": {
                        "discussion": {
                            "fragment_size": 150,
                            "number_of_fragments": 1,
                            "pre_tags": ["<mark>"],
                            "post_tags": ["</mark>"],
                        },
                        "fault_point": {
                            "fragment_size": 150,
                            "number_of_fragments": 1,
                            "pre_tags": ["<mark>"],
                            "post_tags": ["</mark>"],
                        }
                    }
                },
                "_source": [
                    "discussion",
                    "fault_point",
                    "vehiclebrand",
                    "vehicle_brand",
                    "vehicletype",
                    "vehicle_model",
                    "modelyear",
                    "model_year",
                    "brand",
                    "system",
                    "system_name",
                    "part",
                    "component",
                    "component_name",
                    "control_unit",
                    "faultcode",
                    "fault_code",
                    "spare4",
                    "dtc",
                    "searchNum",
                    "search_num",
                    "popularity",
                    "popularity_score",
                    "tags",
                    "labels",
                ],
            }

            response = self.client.search(
                index=INDEX_CONFIG['name'],
                body=search_body,
                size=max(1, size)
            )

            fault_points: List[Dict[str, Any]] = []
            for hit in response.get('hits', {}).get('hits', []):
                doc_id, source = self._extract_source(hit)
                fields = _extract_common_fields(source)
                highlight_dict = hit.get('highlight', {}) or {}
                highlight_text = _select_highlight(
                    highlight_dict,
                    ["fault_point", "discussion"],
                )
                fault_points.append({
                    "id": doc_id,
                    "score": float(hit.get('_score') or 0.0),
                    "discussion": fields.get('discussion', ''),
                    "highlight": highlight_text,
                    "vehiclebrand": fields.get('vehiclebrand'),
                    "vehicletype": fields.get('vehicletype'),
                    "modelyear": fields.get('modelyear'),
                    "system": fields.get('system'),
                    "part": fields.get('part'),
                    "faultcode": fields.get('faultcode') or fields.get('spare4'),
                    "popularity": fields.get('popularity'),
                    "searchNum": fields.get('searchNum'),
                    "tags": fields.get('tags'),
                })

            return {
                "total": response.get('hits', {}).get('total', {}).get('value', 0),
                "fault_points": fault_points,
                "request": {
                    "vehicle_brand": vehicle_brand,
                    "vehicle_name": vehicle_name,
                    "model_year": model_year,
                    "fault_code": fault_code,
                    "control_unit": control_unit,
                    "symptom": symptom,
                    "size": max(1, size),
                }
            }

        except Exception as e:
            logger.error(f"故障点检索失败: {e}")
            return {
                "total": 0,
                "fault_points": [],
                "error": str(e),
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

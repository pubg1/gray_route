#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于 OpenSearch 的故障现象匹配服务
按照 README.md 设计，从 OpenSearch 中查询匹配故障现象
"""

import os
import sys
import logging
from typing import List, Dict, Optional
from opensearchpy import OpenSearch

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG

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

    def search_phenomena(self, 
                        query: str, 
                        system: Optional[str] = None, 
                        part: Optional[str] = None,
                        vehicletype: Optional[str] = None,
                        fault_code: Optional[str] = None,
                        size: int = 10) -> Dict:
        """
        搜索故障现象
        
        Args:
            query: 查询文本
            system: 系统过滤
            part: 部件过滤  
            vehicletype: 车型过滤
            fault_code: 故障码过滤 (spare4字段)
            size: 返回结果数量
            
        Returns:
            搜索结果字典
        """
        try:
            # 构建多字段搜索查询
            search_body = {
                "query": {
                    "bool": {
                        "must": {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "text^3.0",           # 故障现象文本权重最高
                                    "symptoms^2.8",       # 故障症状
                                    "topic^2.5",          # 主题
                                    "discussion^2.5",     # 故障点描述
                                    "spare2^2.3",         # 故障现象描述
                                    "spare4^2.2",         # 故障码 (高权重)
                                    "searchContent^2.0",  # 搜索内容
                                    "search_content^2.0", # 完整内容
                                    "part^2.0",           # 部件信息
                                    "spare1^1.8",         # 系统信息
                                    "spare15^1.8",        # 系统分类
                                    "egon^1.5",           # 故障原因
                                    "vehicletype^1.5",    # 车型信息
                                    "vehiclebrand^1.3",   # 车辆品牌
                                    "search^1.0",         # 原始搜索内容
                                    "solution^1.0",       # 解决方案
                                    "faultcode^0.8"       # 故障码 (备用字段)
                                ],
                                "type": "best_fields",
                                "fuzziness": "AUTO",
                                "minimum_should_match": "75%"
                            }
                        },
                        "filter": [],
                        "should": [
                            # 提升热门案例的权重
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
            
            # 添加过滤条件
            if system:
                search_body["query"]["bool"]["filter"].append({
                    "term": {"system.keyword": system}
                })
            
            if part:
                search_body["query"]["bool"]["filter"].append({
                    "match": {"part": part}
                })
                
            if vehicletype:
                search_body["query"]["bool"]["filter"].append({
                    "term": {"vehicletype.keyword": vehicletype}
                })
            
            if fault_code:
                search_body["query"]["bool"]["filter"].append({
                    "match": {"spare4": fault_code}
                })
            
            # 执行搜索
            response = self.client.search(
                index=INDEX_CONFIG['name'], 
                body=search_body,
                size=size  # 添加 size 参数
            )
            
            # 处理结果
            results = []
            for hit in response['hits']['hits']:
                source = hit['_source']
                
                # 计算综合评分
                base_score = hit['_score']
                popularity_boost = min(source.get('popularity', 0) / 100, 2.0)
                search_boost = min(source.get('searchNum', 0) / 10, 1.0)
                final_score = base_score + popularity_boost + search_boost
                
                result = {
                    "id": hit['_id'],
                    
                    # 核心匹配字段
                    "text": source.get('text', ''),
                    "system": source.get('system', ''),
                    "part": source.get('part', ''),
                    "tags": source.get('tags', []),
                    
                    # 原有重要字段
                    "vehicletype": source.get('vehicletype', ''),
                    "vehiclebrand": source.get('vehiclebrand', ''),
                    "topic": source.get('topic', ''),
                    "symptoms": source.get('symptoms', ''),
                    "discussion": source.get('discussion', ''),
                    "solution": source.get('solution', ''),
                    "egon": source.get('egon', ''),
                    "spare1": source.get('spare1', ''),
                    "spare2": source.get('spare2', ''),
                    "spare4": source.get('spare4', ''),  # 故障码
                    "spare15": source.get('spare15', ''),
                    "faultcode": source.get('faultcode', ''),
                    "createtime": source.get('createtime', ''),
                    "money": source.get('money', ''),
                    
                    # 统计字段
                    "popularity": source.get('popularity', 0),
                    "searchNum": source.get('searchNum', 0),
                    "rate": source.get('rate'),
                    
                    # 评分信息
                    "bm25_score": 0.0,  # OpenSearch 内部计算
                    "cosine": base_score / 10.0,  # 归一化相似度
                    "rerank_score": final_score,
                    "final_score": min(final_score / 10.0, 1.0),  # 归一化到 0-1
                    
                    # 高亮信息
                    "highlight": hit.get('highlight', {}),
                    
                    # 匹配原因
                    "why": self._analyze_match_reason(query, source, hit['_score'])
                }
                results.append(result)
            
            return {
                "query": query,
                "total": response['hits']['total']['value'],
                "top": results
            }
            
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return {
                "query": query,
                "total": 0,
                "top": [],
                "error": str(e)
            }

    def _analyze_match_reason(self, query: str, source: Dict, score: float) -> List[str]:
        """分析匹配原因"""
        reasons = []
        
        # 检查文本相似度
        if score > 5.0:
            reasons.append("语义近")
        elif score > 2.0:
            reasons.append("相关性高")
        
        # 检查系统匹配
        system_keywords = {
            "发动机": ["发动机", "引擎", "启动"],
            "制动": ["刹车", "制动", "ABS"],
            "变速箱/传动": ["变速", "传动", "离合"],
            "电子电气": ["电池", "电路", "传感器"],
            "空调": ["空调", "制冷", "暖风"]
        }
        
        query_lower = query.lower()
        source_system = source.get('system', '')
        
        for system, keywords in system_keywords.items():
            if system == source_system and any(kw in query_lower for kw in keywords):
                reasons.append("系统一致")
                break
        
        # 检查车型匹配
        vehicletype = source.get('vehicletype', '')
        if vehicletype and vehicletype.lower() in query_lower:
            reasons.append("车型匹配")
        
        # 检查热度
        popularity = source.get('popularity', 0)
        if popularity > 100:
            reasons.append("热门案例")
        elif popularity > 50:
            reasons.append("常见问题")
        
        return reasons if reasons else ["文本匹配"]

    def match_with_decision(self, 
                           query: str, 
                           system: Optional[str] = None, 
                           part: Optional[str] = None,
                           fault_code: Optional[str] = None,
                           pass_threshold: float = 0.84,
                           gray_low_threshold: float = 0.65,
                           size: int = 10) -> Dict:
        """
        按照 README.md 设计进行故障现象匹配，包含灰区路由决策
        
        Args:
            query: 查询文本
            system: 系统过滤
            part: 部件过滤
            fault_code: 故障码过滤 (spare4字段)
            pass_threshold: 直接通过阈值
            gray_low_threshold: 灰区下限阈值
            size: 返回结果数量
            
        Returns:
            包含决策信息的匹配结果
        """
        # 获取搜索结果
        search_result = self.search_phenomena(
            query=query, 
            system=system, 
            part=part, 
            fault_code=fault_code,
            size=size
        )
        
        if not search_result["top"]:
            return {
                **search_result,
                "decision": {
                    "mode": "no_match",
                    "chosen_id": None,
                    "confidence": 0.0,
                    "reason": "无匹配结果"
                }
            }
        
        # 获取最佳匹配
        best_match = search_result["top"][0]
        best_score = best_match["final_score"]
        
        # 决策逻辑
        if best_score >= pass_threshold:
            # 直接通过
            decision = {
                "mode": "direct",
                "chosen_id": best_match["id"],
                "confidence": best_score,
                "reason": f"高置信度匹配 (score: {best_score:.3f})"
            }
        elif best_score >= gray_low_threshold:
            # 灰区，需要进一步判断
            decision = {
                "mode": "gray",
                "chosen_id": best_match["id"],
                "confidence": best_score,
                "reason": f"灰区匹配，建议人工确认 (score: {best_score:.3f})",
                "alternatives": [
                    {
                        "id": result["id"],
                        "text": result["text"][:100] + "...",
                        "score": result["final_score"]
                    }
                    for result in search_result["top"][1:4]  # 提供备选方案
                ]
            }
        else:
            # 低置信度，拒绝
            decision = {
                "mode": "reject",
                "chosen_id": None,
                "confidence": best_score,
                "reason": f"置信度过低 (score: {best_score:.3f})",
                "suggestions": [
                    result["text"][:50] + "..."
                    for result in search_result["top"][:3]
                ]
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

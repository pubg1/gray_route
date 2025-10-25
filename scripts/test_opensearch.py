#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenSearch 搜索测试脚本
"""

try:  # pragma: no cover - pytest may not be available during manual execution
    import pytest
except Exception:  # pragma: no cover - keep runtime lightweight when used as script
    pytest = None

if pytest is not None:  # pragma: no cover - applied only in automated test environments
    pytestmark = pytest.mark.skip(
        reason="Manual OpenSearch integration helper; excluded from automated pytest runs."
    )

import json
import sys
from opensearchpy import OpenSearch
from opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG

def test_connection():
    """测试 OpenSearch 连接"""
    try:
        client = OpenSearch([{
            'host': OPENSEARCH_CONFIG['host'], 
            'port': OPENSEARCH_CONFIG['port']
        }])
        
        info = client.info()
        print(f"✅ OpenSearch 连接成功")
        print(f"   版本: {info['version']['number']}")
        print(f"   集群: {info['cluster_name']}")
        return client
    except Exception as e:
        print(f"❌ OpenSearch 连接失败: {e}")
        return None

def test_index_exists(client, index_name):
    """测试索引是否存在"""
    try:
        exists = client.indices.exists(index=index_name)
        if exists:
            # 获取文档数量
            count_result = client.count(index=index_name)
            doc_count = count_result['count']
            print(f"✅ 索引 '{index_name}' 存在，包含 {doc_count} 个文档")
            return True
        else:
            print(f"❌ 索引 '{index_name}' 不存在")
            return False
    except Exception as e:
        print(f"❌ 检查索引失败: {e}")
        return False

def search_test(client, index_name, query, size=5):
    """执行搜索测试"""
    try:
        search_body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["symptoms^2", "discussion^1.5", "solution", "search_content"]
                }
            },
            "size": size,
            "highlight": {
                "fields": {
                    "symptoms": {},
                    "discussion": {},
                    "solution": {}
                }
            }
        }
        
        response = client.search(index=index_name, body=search_body)
        
        hits = response['hits']['hits']
        total = response['hits']['total']['value']
        
        print(f"\n🔍 搜索查询: '{query}'")
        print(f"📊 找到 {total} 个结果，显示前 {len(hits)} 个:")
        print("-" * 60)
        
        for i, hit in enumerate(hits, 1):
            source = hit['_source']
            score = hit['_score']
            
            print(f"{i}. 评分: {score:.2f}")
            print(f"   ID: {source.get('id', 'N/A')}")
            print(f"   车型: {source.get('vehicletype', 'N/A')}")
            print(f"   故障点: {source.get('discussion', 'N/A')}")
            
            # 显示故障现象（截取前100字符）
            symptoms = source.get('symptoms', '')
            if symptoms:
                print(f"   故障现象: {symptoms[:100]}{'...' if len(symptoms) > 100 else ''}")
            
            # 显示高亮内容
            if 'highlight' in hit:
                for field, highlights in hit['highlight'].items():
                    print(f"   高亮({field}): {highlights[0]}")
            
            print()
        
        return True
        
    except Exception as e:
        print(f"❌ 搜索失败: {e}")
        return False

def aggregation_test(client, index_name):
    """聚合测试 - 按车型统计"""
    try:
        agg_body = {
            "size": 0,
            "aggs": {
                "vehicle_types": {
                    "terms": {
                        "field": "vehicletype.keyword",
                        "size": 10
                    }
                }
            }
        }
        
        response = client.search(index=index_name, body=agg_body)
        
        buckets = response['aggregations']['vehicle_types']['buckets']
        
        print(f"\n📈 车型统计 (前10名):")
        print("-" * 30)
        for bucket in buckets:
            vehicle_type = bucket['key']
            doc_count = bucket['doc_count']
            print(f"   {vehicle_type}: {doc_count} 条")
        
        return True
        
    except Exception as e:
        print(f"❌ 聚合查询失败: {e}")
        return False

def main():
    """主函数"""
    print("🧪 OpenSearch 搜索功能测试")
    print("=" * 50)
    
    # 测试连接
    client = test_connection()
    if not client:
        return False
    
    # 测试索引
    index_name = INDEX_CONFIG['name']
    if not test_index_exists(client, index_name):
        print(f"\n💡 提示: 请先运行数据导入脚本")
        print(f"   python run_import.py")
        return False
    
    # 搜索测试用例
    test_queries = [
        "发动机无法启动",
        "刹车发软",
        "变速箱异响", 
        "空调不制冷",
        "方向盘抖动"
    ]
    
    print(f"\n🔍 开始搜索测试...")
    success_count = 0
    
    for query in test_queries:
        if search_test(client, index_name, query, size=3):
            success_count += 1
    
    # 聚合测试
    print(f"\n📊 聚合查询测试...")
    if aggregation_test(client, index_name):
        success_count += 1
    
    # 结果统计
    total_tests = len(test_queries) + 1
    print(f"\n📋 测试结果: {success_count}/{total_tests} 通过")
    
    if success_count == total_tests:
        print("🎉 所有测试通过!")
        
        print(f"\n💡 使用建议:")
        print(f"   - 索引名称: {index_name}")
        print(f"   - OpenSearch 地址: http://{OPENSEARCH_CONFIG['host']}:{OPENSEARCH_CONFIG['port']}")
        print(f"   - 可以集成到应用中进行实时搜索")
        
        return True
    else:
        print("⚠️  部分测试失败，请检查配置和数据")
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 用户中断测试")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试过程出错: {e}")
        sys.exit(1)

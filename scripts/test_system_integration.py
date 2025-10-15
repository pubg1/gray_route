#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统集成测试脚本
测试 OpenSearch 导入和故障现象匹配功能
"""

import sys
import os
import json
import requests
import time
from opensearchpy import OpenSearch
from opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG

def test_opensearch_connection():
    """测试 OpenSearch 连接"""
    print("🔍 测试 OpenSearch 连接...")
    
    try:
        client = OpenSearch(
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
        
        info = client.info()
        print(f"✅ OpenSearch 连接成功: {info['version']['number']}")
        
        # 检查索引
        index_name = INDEX_CONFIG['name']
        if client.indices.exists(index=index_name):
            count = client.count(index=index_name)['count']
            print(f"✅ 索引 '{index_name}' 存在，包含 {count:,} 个文档")
            return True, count
        else:
            print(f"❌ 索引 '{index_name}' 不存在")
            return False, 0
            
    except Exception as e:
        print(f"❌ OpenSearch 连接失败: {e}")
        return False, 0

def test_data_structure():
    """测试数据结构"""
    print("\n🔍 测试数据结构...")
    
    try:
        client = OpenSearch(
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
        
        # 获取一个样本文档
        response = client.search(
            index=INDEX_CONFIG['name'],
            body={"query": {"match_all": {}}, "size": 1}
        )
        
        if response['hits']['hits']:
            doc = response['hits']['hits'][0]
            source = doc['_source']
            
            print(f"✅ 样本文档 ID: {doc['_id']}")
            print(f"   原有字段:")
            print(f"     vehicletype: {source.get('vehicletype', 'N/A')}")
            print(f"     discussion: {source.get('discussion', 'N/A')[:50]}...")
            print(f"     searchNum: {source.get('searchNum', 'N/A')}")
            
            print(f"   新增字段:")
            print(f"     text: {source.get('text', 'N/A')[:50]}...")
            print(f"     system: {source.get('system', 'N/A')}")
            print(f"     part: {source.get('part', 'N/A')[:30]}...")
            print(f"     tags: {source.get('tags', [])}")
            print(f"     popularity: {source.get('popularity', 'N/A')}")
            
            return True
        else:
            print("❌ 没有找到文档")
            return False
            
    except Exception as e:
        print(f"❌ 测试数据结构失败: {e}")
        return False

def test_search_functionality():
    """测试搜索功能"""
    print("\n🔍 测试搜索功能...")
    
    try:
        # 添加项目根目录到路径
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from app.opensearch_matcher import OpenSearchMatcher
        
        matcher = OpenSearchMatcher()
        
        # 测试查询
        test_cases = [
            {
                "query": "发动机无法启动",
                "system": "发动机",
                "expected_keywords": ["发动机", "启动"]
            },
            {
                "query": "刹车发软",
                "system": "制动",
                "expected_keywords": ["刹车", "制动"]
            },
            {
                "query": "变速器挂档冲击",
                "system": "变速箱/传动",
                "expected_keywords": ["变速", "挂档"]
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n测试 {i}: {test_case['query']}")
            
            result = matcher.search_phenomena(
                query=test_case['query'],
                system=test_case['system'],
                size=3
            )
            
            if result['total'] > 0:
                print(f"✅ 找到 {result['total']} 个结果")
                
                for j, match in enumerate(result['results'][:2], 1):
                    print(f"   {j}. [{match['id']}] {match['text'][:60]}...")
                    print(f"      车型: {match['vehicletype']}, 系统: {match['system']}")
                    print(f"      评分: {match['score']:.2f}, 热度: {match['popularity']}")
                    
                    # 检查是否包含预期关键词
                    text_content = match['text'].lower()
                    matched_keywords = [kw for kw in test_case['expected_keywords'] 
                                      if kw in text_content]
                    if matched_keywords:
                        print(f"      ✅ 匹配关键词: {matched_keywords}")
                    else:
                        print(f"      ⚠️  未匹配预期关键词: {test_case['expected_keywords']}")
            else:
                print(f"❌ 没有找到结果")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试搜索功能失败: {e}")
        return False

def test_decision_logic():
    """测试决策逻辑"""
    print("\n🔍 测试灰区路由决策...")
    
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from app.opensearch_matcher import OpenSearchMatcher
        
        matcher = OpenSearchMatcher()
        
        # 测试不同置信度的查询
        test_queries = [
            "发动机无法启动故障灯亮",  # 应该高置信度
            "车辆异常",              # 应该低置信度
            "制动系统问题"           # 应该中等置信度
        ]
        
        for query in test_queries:
            print(f"\n测试查询: {query}")
            
            result = matcher.match_with_decision(
                query=query,
                pass_threshold=0.84,
                gray_low_threshold=0.65
            )
            
            decision = result.get('decision', {})
            mode = decision.get('mode', 'unknown')
            confidence = decision.get('confidence', 0.0)
            
            print(f"   决策模式: {mode}")
            print(f"   置信度: {confidence:.3f}")
            print(f"   原因: {decision.get('reason', 'N/A')}")
            
            if mode == 'direct':
                print(f"   ✅ 直接匹配: {decision.get('chosen_id')}")
            elif mode == 'gray':
                print(f"   ⚠️  灰区匹配，需要确认")
                alternatives = decision.get('alternatives', [])
                if alternatives:
                    print(f"   备选方案: {len(alternatives)} 个")
            elif mode == 'reject':
                print(f"   ❌ 置信度过低，拒绝匹配")
            
        return True
        
    except Exception as e:
        print(f"❌ 测试决策逻辑失败: {e}")
        return False

def test_api_endpoints():
    """测试 API 端点（如果服务正在运行）"""
    print("\n🔍 测试 API 端点...")
    
    base_url = "http://127.0.0.1:8000"
    
    try:
        # 测试健康检查
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ 健康检查通过")
            print(f"   OpenSearch 可用: {health_data.get('opensearch_available', False)}")
            print(f"   数据源: {health_data.get('data_sources', [])}")
            
            # 测试 OpenSearch 匹配端点
            if health_data.get('opensearch_available'):
                test_query = "发动机无法启动"
                response = requests.get(
                    f"{base_url}/opensearch/match",
                    params={"q": test_query, "size": 3},
                    timeout=10
                )
                
                if response.status_code == 200:
                    match_data = response.json()
                    print(f"✅ OpenSearch 匹配 API 正常")
                    print(f"   查询: {match_data.get('query')}")
                    print(f"   结果数: {len(match_data.get('top', []))}")
                    
                    if 'decision' in match_data:
                        decision = match_data['decision']
                        print(f"   决策: {decision.get('mode')} (置信度: {decision.get('confidence', 0):.3f})")
                else:
                    print(f"❌ OpenSearch 匹配 API 失败: {response.status_code}")
            
            return True
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("ℹ️  API 服务未运行，跳过 API 测试")
        print("   可以运行 'python -m app.main' 启动服务后再测试")
        return True
    except Exception as e:
        print(f"❌ API 测试失败: {e}")
        return False

def main():
    """主函数"""
    print("🧪 OpenSearch 系统集成测试")
    print("=" * 60)
    
    tests = [
        ("OpenSearch 连接", test_opensearch_connection),
        ("数据结构", test_data_structure),
        ("搜索功能", test_search_functionality),
        ("决策逻辑", test_decision_logic),
        ("API 端点", test_api_endpoints)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            if test_name == "OpenSearch 连接":
                success, doc_count = test_func()
                if not success:
                    print("\n❌ OpenSearch 连接失败，无法继续测试")
                    break
                results.append((test_name, success))
            else:
                success = test_func()
                results.append((test_name, success))
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            results.append((test_name, False))
    
    # 汇总结果
    print(f"\n{'='*60}")
    print("📊 测试结果汇总:")
    print(f"{'='*60}")
    
    passed = 0
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
        if success:
            passed += 1
    
    total = len(results)
    pass_rate = passed / total if total > 0 else 0
    
    print(f"\n🎯 总体结果: {passed}/{total} 通过 ({pass_rate:.1%})")
    
    if pass_rate >= 0.8:
        print("🎉 系统集成测试基本通过!")
        print("\n💡 下一步:")
        print("   1. 启动 FastAPI 服务: python -m app.main")
        print("   2. 访问 API 文档: http://127.0.0.1:8000/docs")
        print("   3. 测试故障匹配:")
        print("      curl 'http://127.0.0.1:8000/opensearch/match?q=发动机无法启动&system=发动机'")
    elif pass_rate >= 0.5:
        print("⚠️  部分测试失败，请检查配置")
    else:
        print("❌ 系统集成测试失败，请检查 OpenSearch 连接和数据导入")
    
    return pass_rate >= 0.5

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

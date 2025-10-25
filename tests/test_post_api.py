#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 POST 接口的安全性和功能
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="Requires a running API service at 127.0.0.1:8000; skipped in automated tests."
)

import requests
import json
import time

def test_post_api():
    """测试 POST API"""
    print("🧪 测试 OpenSearch POST API")
    print("=" * 50)
    
    base_url = "http://127.0.0.1:8000"
    
    # 测试用例
    test_cases = [
        {
            "name": "基础查询",
            "data": {
                "q": "发动机无法启动",
                "size": 3,
                "use_decision": True
            }
        },
        {
            "name": "系统过滤查询",
            "data": {
                "q": "刹车发软",
                "system": "制动",
                "size": 5,
                "use_decision": True
            }
        },
        {
            "name": "部件过滤查询",
            "data": {
                "q": "变速器挂档延迟",
                "system": "变速箱/传动",
                "part": "变速器",
                "size": 3,
                "use_decision": False
            }
        },
        {
            "name": "复杂查询（安全测试）",
            "data": {
                "q": "发动机故障灯亮 怠速不稳 抖动严重 油耗增加",
                "system": "发动机",
                "part": "发动机控制",
                "vehicletype": "CT4",
                "size": 10,
                "use_decision": True
            }
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. {test_case['name']}")
        print("-" * 30)
        
        try:
            # 发送 POST 请求
            start_time = time.time()
            response = requests.post(
                f"{base_url}/opensearch/match",
                json=test_case['data'],
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            end_time = time.time()
            
            if response.status_code == 200:
                data = response.json()
                
                print(f"✅ 请求成功 ({(end_time - start_time) * 1000:.0f}ms)")
                print(f"   查询: {test_case['data']['q']}")
                print(f"   结果数量: {len(data.get('top', []))}")
                print(f"   总匹配数: {data.get('total', 0)}")
                
                if 'decision' in data:
                    decision = data['decision']
                    print(f"   决策: {decision.get('mode', 'unknown')}")
                    print(f"   置信度: {decision.get('confidence', 0):.3f}")
                
                # 显示前2个结果
                for j, result in enumerate(data.get('top', [])[:2]):
                    print(f"   [{j+1}] ID: {result.get('id', 'N/A')}")
                    print(f"       评分: {result.get('final_score', 0):.3f}")
                    print(f"       系统: {result.get('system', 'N/A')}")
                    
            else:
                print(f"❌ 请求失败: HTTP {response.status_code}")
                print(f"   响应: {response.text[:200]}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 网络错误: {e}")
        except Exception as e:
            print(f"❌ 其他错误: {e}")
    
    print(f"\n🔒 安全性优势:")
    print("   ✅ 查询参数不会出现在 URL 中")
    print("   ✅ 不会被浏览器历史记录")
    print("   ✅ 不会被服务器访问日志记录")
    print("   ✅ 支持复杂的查询结构")
    print("   ✅ 没有 URL 长度限制")

def test_health():
    """测试健康检查"""
    try:
        response = requests.get("http://127.0.0.1:8000/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"🏥 服务状态: {data.get('status', 'unknown')}")
            print(f"   OpenSearch: {'可用' if data.get('opensearch_available') else '不可用'}")
            return True
        else:
            print(f"❌ 健康检查失败: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 无法连接到服务: {e}")
        return False

if __name__ == "__main__":
    print("🚀 OpenSearch POST API 测试")
    print("=" * 60)
    
    # 先检查服务状态
    if test_health():
        print()
        test_post_api()
    else:
        print("\n💡 请先启动服务:")
        print("   python -m app.main")
        print("   或")
        print("   python scripts/start_opensearch_system.py")

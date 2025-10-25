#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汽车故障诊断 API 测试脚本
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="Requires running API service; skip during automated pytest runs."
)

import requests
import json
import time
from typing import Dict, Any, List
import sys
import os

# API配置
BASE_URL = "http://localhost:8000"
TIMEOUT = 30

class APITester:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = []
    
    def test_health(self) -> bool:
        """测试健康检查接口"""
        print("🔍 测试健康检查接口...")
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok":
                    print("✅ 健康检查通过")
                    return True
                else:
                    print(f"❌ 健康检查失败: {data}")
                    return False
            else:
                print(f"❌ 健康检查失败: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ 健康检查异常: {e}")
            return False
    
    def test_match_basic(self) -> bool:
        """测试基础匹配功能"""
        print("\n🔍 测试基础匹配功能...")
        
        test_cases = [
            {
                "query": "刹车发软",
                "expected_system": "制动",
                "description": "制动系统故障"
            },
            {
                "query": "发动机无法启动",
                "expected_system": "发动机", 
                "description": "发动机启动故障"
            },
            {
                "query": "方向盘很重",
                "expected_system": "转向",
                "description": "转向系统故障"
            },
            {
                "query": "空调不制冷",
                "expected_system": "空调",
                "description": "空调系统故障"
            }
        ]
        
        success_count = 0
        for i, case in enumerate(test_cases, 1):
            print(f"  测试用例 {i}: {case['description']}")
            try:
                response = self.session.get(
                    f"{self.base_url}/match",
                    params={"q": case["query"]},
                    timeout=TIMEOUT
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # 检查响应结构
                    required_fields = ["query", "top", "decision"]
                    if all(field in data for field in required_fields):
                        print(f"    ✅ 响应结构正确")
                        
                        # 检查是否有匹配结果
                        if data["top"]:
                            top_result = data["top"][0]
                            actual_system = top_result.get("system", "")
                            confidence = data["decision"].get("confidence", 0.0)
                            
                            print(f"    📊 匹配结果: {top_result.get('text', '')[:50]}...")
                            print(f"    🎯 系统: {actual_system}, 置信度: {confidence:.3f}")
                            
                            # 记录测试结果
                            self.test_results.append({
                                "query": case["query"],
                                "expected_system": case["expected_system"],
                                "actual_system": actual_system,
                                "confidence": confidence,
                                "success": actual_system == case["expected_system"]
                            })
                            
                            if actual_system == case["expected_system"]:
                                print(f"    ✅ 系统匹配正确")
                                success_count += 1
                            else:
                                print(f"    ⚠️  系统匹配不准确 (期望: {case['expected_system']})")
                        else:
                            print(f"    ⚠️  没有找到匹配结果")
                    else:
                        print(f"    ❌ 响应结构不完整")
                else:
                    print(f"    ❌ HTTP错误: {response.status_code}")
                    
            except Exception as e:
                print(f"    ❌ 请求异常: {e}")
            
            print()
        
        accuracy = success_count / len(test_cases) if test_cases else 0
        print(f"📈 基础匹配准确率: {accuracy:.1%} ({success_count}/{len(test_cases)})")
        return accuracy >= 0.5  # 50%以上认为通过
    
    def test_match_with_params(self) -> bool:
        """测试带参数的匹配功能"""
        print("\n🔍 测试参数化匹配功能...")
        
        test_cases = [
            {
                "params": {
                    "q": "刹车发软",
                    "system": "制动",
                    "topn_return": 5
                },
                "description": "指定系统的查询"
            },
            {
                "params": {
                    "q": "发动机故障",
                    "system": "发动机",
                    "model": "宋",
                    "year": "2019"
                },
                "description": "指定车型年份的查询"
            },
            {
                "params": {
                    "q": "异响",
                    "topk_vec": 20,
                    "topk_kw": 20,
                    "topn_return": 1
                },
                "description": "调整搜索参数的查询"
            }
        ]
        
        success_count = 0
        for i, case in enumerate(test_cases, 1):
            print(f"  测试用例 {i}: {case['description']}")
            try:
                response = self.session.get(
                    f"{self.base_url}/match",
                    params=case["params"],
                    timeout=TIMEOUT
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # 检查topn_return参数是否生效
                    expected_count = case["params"].get("topn_return", 3)
                    actual_count = len(data.get("top", []))
                    
                    print(f"    📊 返回结果数: {actual_count} (期望: ≤{expected_count})")
                    
                    if actual_count <= expected_count:
                        print(f"    ✅ 参数生效")
                        success_count += 1
                    else:
                        print(f"    ⚠️  参数可能未生效")
                        
                    # 如果指定了系统，检查是否匹配
                    if "system" in case["params"] and data.get("top"):
                        specified_system = case["params"]["system"]
                        top_result = data["top"][0]
                        if top_result.get("system") == specified_system:
                            print(f"    ✅ 系统过滤生效")
                        else:
                            print(f"    ℹ️  系统过滤可能影响了排序")
                            
                else:
                    print(f"    ❌ HTTP错误: {response.status_code}")
                    
            except Exception as e:
                print(f"    ❌ 请求异常: {e}")
            
            print()
        
        return success_count >= len(test_cases) * 0.7  # 70%以上认为通过
    
    def test_edge_cases(self) -> bool:
        """测试边界情况"""
        print("\n🔍 测试边界情况...")
        
        test_cases = [
            {
                "params": {"q": ""},
                "description": "空查询",
                "expect_error": True
            },
            {
                "params": {"q": "a"},
                "description": "单字符查询",
                "expect_error": False
            },
            {
                "params": {"q": "这是一个非常长的查询语句" * 10},
                "description": "超长查询",
                "expect_error": False
            },
            {
                "params": {"q": "完全不相关的内容比如做饭洗衣服"},
                "description": "不相关查询",
                "expect_error": False
            }
        ]
        
        success_count = 0
        for i, case in enumerate(test_cases, 1):
            print(f"  测试用例 {i}: {case['description']}")
            try:
                response = self.session.get(
                    f"{self.base_url}/match",
                    params=case["params"],
                    timeout=TIMEOUT
                )
                
                if case["expect_error"]:
                    if response.status_code != 200:
                        print(f"    ✅ 正确返回错误 (HTTP {response.status_code})")
                        success_count += 1
                    else:
                        print(f"    ⚠️  应该返回错误但成功了")
                else:
                    if response.status_code == 200:
                        data = response.json()
                        print(f"    ✅ 正常处理边界情况")
                        if case["description"] == "不相关查询":
                            confidence = data.get("decision", {}).get("confidence", 0)
                            if confidence < 0.5:
                                print(f"    ✅ 低置信度处理正确 ({confidence:.3f})")
                            else:
                                print(f"    ⚠️  置信度可能过高 ({confidence:.3f})")
                        success_count += 1
                    else:
                        print(f"    ❌ 处理失败 (HTTP {response.status_code})")
                        
            except Exception as e:
                print(f"    ❌ 请求异常: {e}")
            
            print()
        
        return success_count >= len(test_cases) * 0.7
    
    def test_performance(self) -> bool:
        """测试性能"""
        print("\n🔍 测试性能...")
        
        query = "发动机无法启动"
        response_times = []
        
        print(f"  执行10次查询测试响应时间...")
        for i in range(10):
            try:
                start_time = time.time()
                response = self.session.get(
                    f"{self.base_url}/match",
                    params={"q": query},
                    timeout=TIMEOUT
                )
                end_time = time.time()
                
                if response.status_code == 200:
                    response_time = (end_time - start_time) * 1000  # 转换为毫秒
                    response_times.append(response_time)
                    print(f"    请求 {i+1}: {response_time:.1f}ms")
                else:
                    print(f"    请求 {i+1}: 失败 (HTTP {response.status_code})")
                    
            except Exception as e:
                print(f"    请求 {i+1}: 异常 ({e})")
        
        if response_times:
            avg_time = sum(response_times) / len(response_times)
            max_time = max(response_times)
            min_time = min(response_times)
            
            print(f"\n  📊 性能统计:")
            print(f"    平均响应时间: {avg_time:.1f}ms")
            print(f"    最大响应时间: {max_time:.1f}ms")
            print(f"    最小响应时间: {min_time:.1f}ms")
            
            # 性能要求：平均响应时间 < 500ms
            if avg_time < 500:
                print(f"    ✅ 性能测试通过")
                return True
            else:
                print(f"    ⚠️  响应时间较慢")
                return False
        else:
            print(f"    ❌ 性能测试失败")
            return False
    
    def generate_report(self):
        """生成测试报告"""
        print("\n" + "="*60)
        print("📋 测试报告")
        print("="*60)
        
        if self.test_results:
            print(f"\n详细匹配结果:")
            for result in self.test_results:
                status = "✅" if result["success"] else "❌"
                print(f"  {status} {result['query']} -> {result['actual_system']} (置信度: {result['confidence']:.3f})")
        
        print(f"\n测试完成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    def run_all_tests(self) -> bool:
        """运行所有测试"""
        print("🚀 开始API测试")
        print("="*60)
        
        tests = [
            ("健康检查", self.test_health),
            ("基础匹配", self.test_match_basic),
            ("参数化匹配", self.test_match_with_params),
            ("边界情况", self.test_edge_cases),
            ("性能测试", self.test_performance)
        ]
        
        results = []
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append((test_name, result))
                status = "✅ 通过" if result else "❌ 失败"
                print(f"{test_name}: {status}")
            except Exception as e:
                print(f"{test_name}: ❌ 异常 - {e}")
                results.append((test_name, False))
        
        self.generate_report()
        
        # 计算总体通过率
        passed = sum(1 for _, result in results if result)
        total = len(results)
        pass_rate = passed / total if total > 0 else 0
        
        print(f"\n🎯 总体测试结果: {passed}/{total} 通过 ({pass_rate:.1%})")
        
        if pass_rate >= 0.8:
            print("🎉 API测试整体通过！")
            return True
        else:
            print("⚠️  API测试存在问题，请检查服务状态")
            return False

def main():
    """主函数"""
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    else:
        base_url = BASE_URL
    
    print(f"🔗 测试目标: {base_url}")
    
    tester = APITester(base_url)
    success = tester.run_all_tests()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

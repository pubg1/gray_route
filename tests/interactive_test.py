#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交互式API测试工具
"""

import requests
import json
from typing import Dict, Any
import sys

BASE_URL = "http://localhost:8000"

def format_response(data: Dict[str, Any]) -> str:
    """格式化响应数据"""
    output = []
    
    # 查询信息
    output.append(f"🔍 查询: {data.get('query', 'N/A')}")
    
    # 决策信息
    decision = data.get('decision', {})
    mode = decision.get('mode', 'unknown')
    confidence = decision.get('confidence', 0.0)
    chosen_id = decision.get('chosen_id', 'None')
    
    mode_emoji = {
        'direct': '🎯',
        'llm': '🤖', 
        'fallback': '🔄'
    }
    
    output.append(f"{mode_emoji.get(mode, '❓')} 决策: {mode} (置信度: {confidence:.3f})")
    output.append(f"📌 推荐ID: {chosen_id}")
    
    # 匹配结果
    top_results = data.get('top', [])
    if top_results:
        output.append(f"\n📋 匹配结果 (共{len(top_results)}条):")
        for i, result in enumerate(top_results, 1):
            output.append(f"\n  {i}. ID: {result.get('id', 'N/A')}")
            output.append(f"     故障: {result.get('text', 'N/A')}")
            output.append(f"     系统: {result.get('system', 'N/A')} | 部件: {result.get('part', 'N/A')}")
            
            # 分数信息
            scores = []
            if result.get('final_score'):
                scores.append(f"综合: {result['final_score']:.3f}")
            if result.get('rerank_score'):
                scores.append(f"重排: {result['rerank_score']:.3f}")
            if result.get('cosine'):
                scores.append(f"语义: {result['cosine']:.3f}")
            if result.get('bm25_score'):
                scores.append(f"关键词: {result['bm25_score']:.3f}")
            if result.get('popularity'):
                scores.append(f"热度: {result['popularity']:.0f}")
            
            if scores:
                output.append(f"     分数: {' | '.join(scores)}")
            
            # 匹配原因
            why = result.get('why', [])
            if why:
                output.append(f"     原因: {', '.join(why)}")
            
            # 标签
            tags = result.get('tags', [])
            if tags:
                output.append(f"     标签: {', '.join(tags[:5])}")  # 只显示前5个标签
    else:
        output.append("\n❌ 没有找到匹配结果")
    
    return '\n'.join(output)

def test_query(base_url: str, query: str, **params) -> None:
    """测试单个查询"""
    try:
        # 构建请求参数
        request_params = {'q': query}
        request_params.update(params)
        
        print(f"🚀 发送请求...")
        print(f"   URL: {base_url}/match")
        print(f"   参数: {request_params}")
        print("-" * 60)
        
        # 发送请求
        response = requests.get(f"{base_url}/match", params=request_params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(format_response(data))
        else:
            print(f"❌ 请求失败: HTTP {response.status_code}")
            try:
                error_data = response.json()
                print(f"错误详情: {error_data}")
            except:
                print(f"响应内容: {response.text}")
                
    except requests.exceptions.Timeout:
        print("❌ 请求超时")
    except requests.exceptions.ConnectionError:
        print("❌ 连接失败，请确保服务正在运行")
    except Exception as e:
        print(f"❌ 请求异常: {e}")

def interactive_mode(base_url: str):
    """交互式模式"""
    print("🎮 交互式测试模式")
    print("=" * 60)
    print("输入故障描述进行测试，输入 'quit' 退出")
    print("支持的参数格式: 查询内容 [system=系统] [part=部件] [topn=数量]")
    print("示例: 刹车发软 system=制动 topn=5")
    print("-" * 60)
    
    while True:
        try:
            user_input = input("\n🔍 请输入查询: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 再见！")
                break
            
            if not user_input:
                continue
            
            # 解析输入
            parts = user_input.split()
            query = parts[0]
            params = {}
            
            for part in parts[1:]:
                if '=' in part:
                    key, value = part.split('=', 1)
                    if key == 'topn':
                        params['topn_return'] = int(value)
                    elif key in ['system', 'part', 'model', 'year']:
                        params[key] = value
                    elif key == 'topk_vec':
                        params['topk_vec'] = int(value)
                    elif key == 'topk_kw':
                        params['topk_kw'] = int(value)
                else:
                    query += ' ' + part
            
            print()
            test_query(base_url, query, **params)
            
        except KeyboardInterrupt:
            print("\n👋 再见！")
            break
        except Exception as e:
            print(f"❌ 输入处理错误: {e}")

def batch_test_mode(base_url: str):
    """批量测试模式"""
    test_cases = [
        {"query": "刹车发软", "description": "制动系统故障"},
        {"query": "发动机无法启动", "description": "启动故障"},
        {"query": "方向盘很重", "description": "转向助力故障"},
        {"query": "空调不制冷", "description": "空调系统故障"},
        {"query": "发动机抖动", "description": "发动机运行不稳"},
        {"query": "变速箱顿挫", "description": "变速箱故障"},
        {"query": "车身异响", "description": "底盘悬挂问题"},
        {"query": "大灯不亮", "description": "电气系统故障"},
    ]
    
    print("🔄 批量测试模式")
    print("=" * 60)
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试 {i}/{len(test_cases)}: {case['description']}")
        print("=" * 40)
        test_query(base_url, case['query'])
        
        if i < len(test_cases):
            input("\n按回车继续下一个测试...")

def main():
    """主函数"""
    base_url = BASE_URL
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    
    print(f"🔗 API地址: {base_url}")
    
    # 健康检查
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ 服务状态正常")
        else:
            print(f"⚠️  服务状态异常: HTTP {response.status_code}")
    except:
        print("❌ 无法连接到服务，请确保服务正在运行")
        return
    
    print("\n请选择测试模式:")
    print("1. 交互式测试")
    print("2. 批量测试")
    print("3. 单次测试")
    
    while True:
        try:
            choice = input("\n请输入选择 (1-3): ").strip()
            
            if choice == '1':
                interactive_mode(base_url)
                break
            elif choice == '2':
                batch_test_mode(base_url)
                break
            elif choice == '3':
                query = input("请输入查询内容: ").strip()
                if query:
                    print()
                    test_query(base_url, query)
                break
            else:
                print("无效选择，请输入 1-3")
                
        except KeyboardInterrupt:
            print("\n👋 再见！")
            break

if __name__ == "__main__":
    main()

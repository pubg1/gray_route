#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenSearch 故障现象匹配系统启动脚本
最终验证和启动完整系统
"""

import os
import sys
import time
import subprocess
import threading
import requests
import json
from datetime import datetime

def print_banner():
    """打印启动横幅"""
    print("=" * 80)
    print("🚀 OpenSearch 故障现象匹配系统")
    print("   基于 servicingcase_last.json 的智能故障诊断")
    print("   按照 README.md 设计，保留所有原有字段")
    print("=" * 80)
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

def check_prerequisites():
    """检查前置条件"""
    print("📋 检查系统前置条件...")
    
    checks = []
    
    # 检查 Python 版本
    python_version = sys.version_info
    if python_version >= (3, 8):
        print(f"✅ Python 版本: {python_version.major}.{python_version.minor}")
        checks.append(True)
    else:
        print(f"❌ Python 版本过低: {python_version.major}.{python_version.minor} (需要 3.8+)")
        checks.append(False)
    
    # 检查必要文件
    required_files = [
        "../data/servicingcase_last.json",
        "opensearch_config.py",
        "import_to_opensearch_preserve_fields.py",
        "../app/opensearch_matcher.py",
        "../app/main.py"
    ]
    
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✅ 文件存在: {os.path.basename(file_path)}")
            checks.append(True)
        else:
            print(f"❌ 文件缺失: {file_path}")
            checks.append(False)
    
    # 检查 OpenSearch 依赖
    try:
        from opensearchpy import OpenSearch
        print("✅ opensearch-py 已安装")
        checks.append(True)
    except ImportError:
        print("❌ opensearch-py 未安装")
        checks.append(False)
    
    success_rate = sum(checks) / len(checks)
    print(f"\n📊 前置条件检查: {sum(checks)}/{len(checks)} 通过 ({success_rate:.1%})")
    
    return success_rate >= 0.8

def test_opensearch_connection():
    """测试 OpenSearch 连接"""
    print("\n🔗 测试 OpenSearch 连接...")
    
    try:
        from opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG
        from opensearchpy import OpenSearch
        
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
        
        # 测试连接
        info = client.info()
        print(f"✅ OpenSearch 连接成功")
        print(f"   版本: {info['version']['number']}")
        print(f"   集群: {info['cluster_name']}")
        
        # 检查索引
        index_name = INDEX_CONFIG['name']
        if client.indices.exists(index=index_name):
            count = client.count(index=index_name)['count']
            print(f"✅ 索引 '{index_name}' 存在，包含 {count:,} 个文档")
            
            if count == 0:
                print("⚠️  索引为空，需要导入数据")
                return True, False  # 连接成功，但需要导入数据
            else:
                return True, True   # 连接成功，数据已存在
        else:
            print(f"⚠️  索引 '{index_name}' 不存在，需要创建和导入数据")
            return True, False
            
    except Exception as e:
        print(f"❌ OpenSearch 连接失败: {e}")
        return False, False

def import_data_if_needed(has_data):
    """如果需要，导入数据"""
    if has_data:
        print("\n📊 数据已存在，跳过导入")
        return True
    
    print("\n📊 开始数据导入...")
    print("选择导入方式:")
    print("   1. 快速导入（推荐）")
    print("   2. 清除现有数据后导入")
    print("   3. 跳过导入")
    
    while True:
        choice = input("请选择 (1/2/3): ").strip()
        if choice in ['1', '2', '3']:
            break
        print("❌ 无效选择")
    
    if choice == '3':
        print("⏭️  跳过数据导入")
        return False
    
    if choice == '2':
        print("🗑️  清除现有数据...")
        os.system("python quick_clear_index.py")
    
    print("📥 导入数据...")
    result = os.system("python import_to_opensearch_preserve_fields.py")
    
    if result == 0:
        print("✅ 数据导入成功")
        return True
    else:
        print("❌ 数据导入失败")
        return False

def start_api_server():
    """启动 API 服务器"""
    print("\n🚀 启动 FastAPI 服务器...")
    
    # 切换到项目根目录
    os.chdir("..")
    
    # 启动服务器
    try:
        # 尝试使用 uvicorn
        cmd = ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
        print(f"   命令: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        return process
        
    except FileNotFoundError:
        # 如果没有 uvicorn，使用直接运行
        print("   使用直接运行模式...")
        cmd = ["python", "-m", "app.main"]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        return process

def wait_for_server(max_wait=30):
    """等待服务器启动"""
    print("⏳ 等待服务器启动...")
    
    for i in range(max_wait):
        try:
            response = requests.get("http://127.0.0.1:8000/health", timeout=2)
            if response.status_code == 200:
                health_data = response.json()
                print(f"✅ 服务器启动成功 (耗时 {i+1}s)")
                print(f"   状态: {health_data.get('status')}")
                print(f"   OpenSearch 可用: {health_data.get('opensearch_available', False)}")
                return True
        except:
            pass
        
        time.sleep(1)
        if i % 5 == 4:
            print(f"   等待中... ({i+1}s)")
    
    print("❌ 服务器启动超时")
    return False

def run_integration_tests():
    """运行集成测试"""
    print("\n🧪 运行集成测试...")
    
    test_cases = [
        {
            "name": "健康检查",
            "url": "http://127.0.0.1:8000/health",
            "expected_keys": ["status", "opensearch_available"]
        },
        {
            "name": "OpenSearch 故障匹配",
            "url": "http://127.0.0.1:8000/opensearch/match?q=发动机无法启动&size=3",
            "expected_keys": ["query", "total", "top"]
        },
        {
            "name": "系统过滤搜索",
            "url": "http://127.0.0.1:8000/opensearch/match?q=刹车发软&system=制动&size=3",
            "expected_keys": ["query", "total", "top"]
        },
        {
            "name": "统计信息",
            "url": "http://127.0.0.1:8000/opensearch/stats",
            "expected_keys": ["total_documents"]
        }
    ]
    
    passed = 0
    for test in test_cases:
        try:
            response = requests.get(test["url"], timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                # 检查是否包含预期字段
                has_expected = all(key in data for key in test["expected_keys"])
                
                if has_expected:
                    print(f"✅ {test['name']}")
                    if "total" in data:
                        print(f"   找到 {data.get('total', 0)} 个结果")
                    passed += 1
                else:
                    print(f"❌ {test['name']} - 响应格式不正确")
            else:
                print(f"❌ {test['name']} - HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ {test['name']} - {e}")
    
    success_rate = passed / len(test_cases)
    print(f"\n📊 集成测试结果: {passed}/{len(test_cases)} 通过 ({success_rate:.1%})")
    
    return success_rate >= 0.75

def show_usage_examples():
    """显示使用示例"""
    print("\n📖 使用示例:")
    print("=" * 50)
    
    examples = [
        {
            "description": "基础故障查询",
            "curl": "curl 'http://127.0.0.1:8000/opensearch/match?q=发动机无法启动'"
        },
        {
            "description": "系统过滤查询",
            "curl": "curl 'http://127.0.0.1:8000/opensearch/match?q=刹车发软&system=制动'"
        },
        {
            "description": "车型过滤查询",
            "curl": "curl 'http://127.0.0.1:8000/opensearch/match?q=故障灯亮&vehicletype=CT4'"
        },
        {
            "description": "混合匹配（推荐）",
            "curl": "curl 'http://127.0.0.1:8000/match/hybrid?q=变速器挂档冲击&system=变速箱/传动'"
        },
        {
            "description": "获取统计信息",
            "curl": "curl 'http://127.0.0.1:8000/opensearch/stats'"
        }
    ]
    
    for example in examples:
        print(f"\n💡 {example['description']}:")
        print(f"   {example['curl']}")
    
    print(f"\n🌐 Web 界面:")
    print(f"   API 文档: http://127.0.0.1:8000/docs")
    print(f"   交互式测试: http://127.0.0.1:8000/redoc")

def main():
    """主函数"""
    print_banner()
    
    # 1. 检查前置条件
    if not check_prerequisites():
        print("\n❌ 前置条件检查失败，请先解决上述问题")
        return False
    
    # 2. 测试 OpenSearch 连接
    connected, has_data = test_opensearch_connection()
    if not connected:
        print("\n❌ OpenSearch 连接失败，请检查配置")
        print("💡 提示:")
        print("   1. 检查 VPC 端点连接: python test_vpc_connection.py")
        print("   2. 确认在正确的网络环境中（VPC 内部）")
        print("   3. 验证认证信息是否正确")
        return False
    
    # 3. 导入数据（如果需要）
    if not import_data_if_needed(has_data):
        print("\n⚠️  没有数据，某些功能可能不可用")
    
    # 4. 启动 API 服务器
    try:
        server_process = start_api_server()
        
        # 5. 等待服务器启动
        if not wait_for_server():
            print("❌ 服务器启动失败")
            server_process.terminate()
            return False
        
        # 6. 运行集成测试
        if run_integration_tests():
            print("\n🎉 系统启动成功!")
        else:
            print("\n⚠️  系统启动完成，但部分功能可能有问题")
        
        # 7. 显示使用示例
        show_usage_examples()
        
        print("\n" + "=" * 80)
        print("🎯 系统已就绪!")
        print("   - 服务地址: http://127.0.0.1:8000")
        print("   - API 文档: http://127.0.0.1:8000/docs")
        print("   - 按 Ctrl+C 停止服务")
        print("=" * 80)
        
        # 8. 保持服务运行
        try:
            while True:
                line = server_process.stdout.readline()
                if line:
                    print(f"[SERVER] {line.strip()}")
                elif server_process.poll() is not None:
                    break
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n👋 正在停止服务...")
            server_process.terminate()
            server_process.wait()
            print("✅ 服务已停止")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 启动过程出错: {e}")
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 用户中断启动")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 启动异常: {e}")
        sys.exit(1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键设置 OpenSearch 故障现象匹配系统
完整的自动化部署脚本
"""

import os
import sys
import time
import json
from datetime import datetime

def print_header():
    """打印标题"""
    print("🚀" + "=" * 78 + "🚀")
    print("   OpenSearch 故障现象匹配系统 - 一键部署")
    print("   基于 servicingcase_last.json 的智能故障诊断")
    print("   保留所有原有字段，按照 README.md 设计实现")
    print("🚀" + "=" * 78 + "🚀")
    print()

def check_environment():
    """检查环境"""
    print("🔍 环境检查...")
    
    # 检查 Python 版本
    if sys.version_info < (3, 8):
        print(f"❌ Python 版本过低: {sys.version_info.major}.{sys.version_info.minor} (需要 3.8+)")
        return False
    print(f"✅ Python 版本: {sys.version_info.major}.{sys.version_info.minor}")
    
    # 检查数据文件
    data_file = "../data/servicingcase_last.json"
    if not os.path.exists(data_file):
        print(f"❌ 数据文件不存在: {data_file}")
        return False
    print(f"✅ 数据文件存在")
    
    # 检查配置文件
    config_file = "opensearch_config.py"
    if not os.path.exists(config_file):
        print(f"❌ 配置文件不存在: {config_file}")
        return False
    print(f"✅ 配置文件存在")
    
    return True

def install_dependencies():
    """安装依赖"""
    print("\n📦 安装依赖...")
    result = os.system("python install_opensearch_deps.py")
    if result == 0:
        print("✅ 依赖安装成功")
        return True
    else:
        print("❌ 依赖安装失败")
        return False

def test_connection():
    """测试连接"""
    print("\n🔗 测试 OpenSearch 连接...")
    
    try:
        from opensearch_config import OPENSEARCH_CONFIG
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
            timeout=10  # 短超时用于快速测试
        )
        
        info = client.info()
        print(f"✅ 连接成功: {info['cluster_name']} v{info['version']['number']}")
        return True
        
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        print("💡 请确保:")
        print("   1. 在正确的网络环境中（VPC 内部）")
        print("   2. OpenSearch 服务正常运行")
        print("   3. 认证信息正确")
        return False

def setup_data():
    """设置数据"""
    print("\n📊 数据设置...")
    
    print("选择数据设置方式:")
    print("   1. 全新导入（推荐）- 清除现有数据并导入")
    print("   2. 增量导入 - 直接导入，不删除现有数据")
    print("   3. 跳过数据导入")
    
    while True:
        choice = input("请选择 (1/2/3): ").strip()
        if choice in ['1', '2', '3']:
            break
        print("❌ 无效选择，请输入 1、2 或 3")
    
    if choice == '3':
        print("⏭️  跳过数据导入")
        return True
    
    if choice == '1':
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

def run_tests():
    """运行测试"""
    print("\n🧪 运行快速测试...")
    
    try:
        from opensearch_config import INDEX_CONFIG
        from opensearchpy import OpenSearch
        from opensearch_config import OPENSEARCH_CONFIG
        
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
        
        # 测试索引存在
        index_name = INDEX_CONFIG['name']
        if client.indices.exists(index=index_name):
            count = client.count(index=index_name)['count']
            print(f"✅ 索引测试通过: {count:,} 个文档")
        else:
            print("⚠️  索引不存在")
            return False
        
        # 测试搜索功能
        response = client.search(
            index=index_name,
            body={
                "query": {"match": {"text": "发动机"}},
                "size": 1
            }
        )
        
        if response['hits']['total']['value'] > 0:
            print("✅ 搜索功能测试通过")
        else:
            print("⚠️  搜索功能测试失败")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def create_startup_info():
    """创建启动信息文件"""
    startup_info = {
        "system": "OpenSearch 故障现象匹配系统",
        "setup_time": datetime.now().isoformat(),
        "status": "ready",
        "endpoints": {
            "health": "http://127.0.0.1:8000/health",
            "opensearch_match": "http://127.0.0.1:8000/opensearch/match",
            "hybrid_match": "http://127.0.0.1:8000/match/hybrid",
            "stats": "http://127.0.0.1:8000/opensearch/stats",
            "docs": "http://127.0.0.1:8000/docs"
        },
        "examples": {
            "basic_search": "curl 'http://127.0.0.1:8000/opensearch/match?q=发动机无法启动'",
            "system_filter": "curl 'http://127.0.0.1:8000/opensearch/match?q=刹车发软&system=制动'",
            "hybrid_match": "curl 'http://127.0.0.1:8000/match/hybrid?q=变速器挂档冲击'"
        },
        "start_command": "python start_opensearch_system.py"
    }
    
    with open("system_ready.json", "w", encoding="utf-8") as f:
        json.dump(startup_info, f, ensure_ascii=False, indent=2)
    
    print("✅ 创建启动信息文件: system_ready.json")

def show_completion_info():
    """显示完成信息"""
    print("\n" + "🎉" + "=" * 78 + "🎉")
    print("   系统设置完成！")
    print("🎉" + "=" * 78 + "🎉")
    
    print("\n📋 系统特性:")
    print("   ✅ 保留 servicingcase_last.json 所有原有字段和 ID")
    print("   ✅ 智能故障现象匹配和系统分类")
    print("   ✅ 灰区路由决策（0.65-0.84 阈值）")
    print("   ✅ 多维度搜索（故障现象、系统、车型、部件）")
    print("   ✅ 混合匹配（本地索引 + OpenSearch）")
    
    print("\n🚀 启动系统:")
    print("   python start_opensearch_system.py")
    print("   # 或者手动启动")
    print("   cd ..")
    print("   python -m app.main")
    
    print("\n🔍 测试 API:")
    print("   # 健康检查")
    print("   curl http://127.0.0.1:8000/health")
    print()
    print("   # 故障匹配")
    print("   curl 'http://127.0.0.1:8000/opensearch/match?q=发动机无法启动'")
    print()
    print("   # 系统过滤")
    print("   curl 'http://127.0.0.1:8000/opensearch/match?q=刹车发软&system=制动'")
    print()
    print("   # 混合匹配")
    print("   curl 'http://127.0.0.1:8000/match/hybrid?q=变速器挂档冲击'")
    
    print("\n📖 文档:")
    print("   - API 文档: http://127.0.0.1:8000/docs")
    print("   - 详细说明: OpenSearch_Integration_README.md")
    print("   - 完成报告: OPENSEARCH_SYSTEM_COMPLETE.md")
    
    print("\n💡 下一步:")
    print("   1. 运行 'python start_opensearch_system.py' 启动完整系统")
    print("   2. 访问 http://127.0.0.1:8000/docs 查看 API 文档")
    print("   3. 使用 'python example_queries.py' 运行示例查询")

def main():
    """主函数"""
    print_header()
    
    steps = [
        ("环境检查", check_environment),
        ("安装依赖", install_dependencies),
        ("测试连接", test_connection),
        ("设置数据", setup_data),
        ("运行测试", run_tests)
    ]
    
    for i, (step_name, step_func) in enumerate(steps, 1):
        print(f"\n📍 步骤 {i}/{len(steps)}: {step_name}")
        print("-" * 50)
        
        if not step_func():
            print(f"\n❌ 步骤 {i} 失败: {step_name}")
            print("请解决上述问题后重新运行")
            return False
        
        print(f"✅ 步骤 {i} 完成: {step_name}")
    
    # 创建启动信息
    create_startup_info()
    
    # 显示完成信息
    show_completion_info()
    
    # 询问是否立即启动
    print("\n" + "=" * 80)
    start_now = input("是否立即启动系统？(Y/n): ").strip().lower()
    
    if start_now in ['', 'y', 'yes']:
        print("\n🚀 启动系统...")
        os.system("python start_opensearch_system.py")
    else:
        print("\n👋 设置完成，稍后可运行 'python start_opensearch_system.py' 启动系统")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 用户中断设置")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 设置过程出错: {e}")
        sys.exit(1)

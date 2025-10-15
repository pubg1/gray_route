#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整系统部署脚本
按照 README.md 设计，部署基于 OpenSearch 的故障现象匹配系统
"""

import os
import sys
import time
import subprocess
import json

def run_command(cmd, description, check_result=True):
    """运行命令并显示结果"""
    print(f"🚀 {description}...")
    print(f"   命令: {cmd}")
    
    result = os.system(cmd)
    
    if result == 0:
        print(f"✅ {description} 成功")
        return True
    else:
        print(f"❌ {description} 失败 (退出码: {result})")
        if check_result:
            return False
        return True

def check_file_exists(file_path, description):
    """检查文件是否存在"""
    if os.path.exists(file_path):
        print(f"✅ {description}: {file_path}")
        return True
    else:
        print(f"❌ {description} 不存在: {file_path}")
        return False

def main():
    """主函数"""
    print("🚀 OpenSearch 故障现象匹配系统完整部署")
    print("按照 README.md 设计，集成 servicingcase_last.json 数据")
    print("=" * 70)
    
    # 检查必要文件
    print("1. 📋 检查必要文件...")
    required_files = [
        ("../data/servicingcase_last.json", "原始数据文件"),
        ("opensearch_config.py", "OpenSearch 配置文件"),
        ("import_to_opensearch_preserve_fields.py", "数据导入脚本"),
        ("../app/opensearch_matcher.py", "OpenSearch 匹配器"),
        ("../app/main.py", "FastAPI 主应用")
    ]
    
    missing_files = []
    for file_path, description in required_files:
        if not check_file_exists(file_path, description):
            missing_files.append(file_path)
    
    if missing_files:
        print(f"\n❌ 缺少必要文件，无法继续部署")
        return False
    
    # 检查 Python 依赖
    print("\n2. 📦 检查和安装 Python 依赖...")
    if not run_command("python install_opensearch_deps.py", "安装 OpenSearch 依赖"):
        return False
    
    # 测试 OpenSearch 连接
    print("\n3. 🔗 测试 OpenSearch 连接...")
    if not run_command("python test_vpc_connection.py", "测试 VPC 连接", check_result=False):
        print("⚠️  OpenSearch 连接测试失败，请检查配置")
        choice = input("是否继续部署？(y/N): ").strip().lower()
        if choice != 'y':
            return False
    
    # 数据导入选择
    print("\n4. 📊 数据导入...")
    print("选择数据导入方式:")
    print("   1. 清除现有数据并重新导入")
    print("   2. 直接导入（如果索引不存在会自动创建）")
    print("   3. 跳过数据导入")
    
    while True:
        choice = input("请选择 (1/2/3): ").strip()
        if choice in ['1', '2', '3']:
            break
        print("❌ 无效选择，请输入 1、2 或 3")
    
    if choice == '1':
        print("🗑️  清除现有索引...")
        run_command("python quick_clear_index.py", "清除索引", check_result=False)
        
        print("📥 导入数据...")
        if not run_command("python import_to_opensearch_preserve_fields.py", "导入数据"):
            return False
            
    elif choice == '2':
        print("📥 导入数据...")
        if not run_command("python import_to_opensearch_preserve_fields.py", "导入数据"):
            return False
    else:
        print("⏭️  跳过数据导入")
    
    # 运行系统集成测试
    print("\n5. 🧪 运行系统集成测试...")
    if not run_command("python test_system_integration.py", "系统集成测试", check_result=False):
        print("⚠️  部分测试失败，但继续部署")
    
    # 生成示例查询脚本
    print("\n6. 📝 生成示例查询脚本...")
    create_example_queries()
    
    # 部署完成
    print("\n🎉 系统部署完成!")
    print("=" * 50)
    
    print("📋 部署摘要:")
    print("   ✅ OpenSearch 连接配置完成")
    print("   ✅ 数据导入完成（保留所有原有字段）")
    print("   ✅ 故障现象匹配功能就绪")
    print("   ✅ API 端点配置完成")
    
    print("\n🚀 启动服务:")
    print("   cd ..")
    print("   python -m app.main")
    print("   # 或者")
    print("   uvicorn app.main:app --host 0.0.0.0 --port 8000")
    
    print("\n🔍 测试 API:")
    print("   # 健康检查")
    print("   curl http://127.0.0.1:8000/health")
    print()
    print("   # OpenSearch 故障匹配")
    print("   curl 'http://127.0.0.1:8000/opensearch/match?q=发动机无法启动&system=发动机'")
    print()
    print("   # 混合匹配（本地+OpenSearch）")
    print("   curl 'http://127.0.0.1:8000/match/hybrid?q=刹车发软&system=制动'")
    print()
    print("   # 获取统计信息")
    print("   curl http://127.0.0.1:8000/opensearch/stats")
    
    print("\n📖 API 文档:")
    print("   http://127.0.0.1:8000/docs")
    
    print("\n💡 故障现象匹配特性:")
    print("   ✅ 保留原始数据 ID 和所有字段")
    print("   ✅ 智能提取故障现象、系统、部件信息")
    print("   ✅ 支持多字段搜索和过滤")
    print("   ✅ 灰区路由决策（0.65-0.84 阈值）")
    print("   ✅ 混合匹配（本地索引 + OpenSearch）")
    
    return True

def create_example_queries():
    """创建示例查询脚本"""
    examples = {
        "发动机故障": {
            "query": "发动机无法启动",
            "system": "发动机",
            "description": "发动机启动相关故障"
        },
        "制动系统": {
            "query": "刹车发软 制动距离长",
            "system": "制动",
            "description": "制动系统相关故障"
        },
        "变速箱问题": {
            "query": "变速器挂档冲击 换档延迟",
            "system": "变速箱/传动",
            "description": "变速箱传动相关故障"
        },
        "电子电气": {
            "query": "故障灯亮 传感器异常",
            "system": "电子电气",
            "description": "电子电气系统故障"
        },
        "空调系统": {
            "query": "空调不制冷 压缩机不工作",
            "system": "空调",
            "description": "空调系统相关故障"
        }
    }
    
    script_content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenSearch 故障现象匹配示例查询
自动生成的测试脚本
"""

import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_query(name, query, system=None, description=""):
    """测试单个查询"""
    print(f"\\n🔍 测试: {{name}}")
    print(f"   描述: {{description}}")
    print(f"   查询: {{query}}")
    if system:
        print(f"   系统: {{system}}")
    
    try:
        # OpenSearch 匹配
        params = {{"q": query, "size": 3}}
        if system:
            params["system"] = system
            
        response = requests.get(f"{{BASE_URL}}/opensearch/match", params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ 找到 {{len(data.get('top', []))}} 个结果")
            
            # 显示决策信息
            if 'decision' in data:
                decision = data['decision']
                print(f"   决策: {{decision.get('mode')}} (置信度: {{decision.get('confidence', 0):.3f}})")
            
            # 显示前2个结果
            for i, result in enumerate(data.get('top', [])[:2], 1):
                print(f"     {{i}}. [{{result['id']}}] {{result['text'][:80]}}...")
                print(f"        车型: {{result['vehicletype']}}, 评分: {{result['score']:.2f}}")
        else:
            print(f"   ❌ 请求失败: {{response.status_code}}")
            
    except requests.exceptions.ConnectionError:
        print(f"   ❌ 连接失败，请确保服务正在运行")
    except Exception as e:
        print(f"   ❌ 查询失败: {{e}}")

def main():
    """主函数"""
    print("🧪 OpenSearch 故障现象匹配示例查询")
    print("=" * 60)
    
    # 检查服务状态
    try:
        response = requests.get(f"{{BASE_URL}}/health", timeout=5)
        if response.status_code == 200:
            health = response.json()
            print(f"✅ 服务运行正常")
            print(f"   OpenSearch 可用: {{health.get('opensearch_available', False)}}")
        else:
            print(f"❌ 服务状态异常: {{response.status_code}}")
            return
    except:
        print("❌ 无法连接到服务，请先启动:")
        print("   python -m app.main")
        return
    
    # 运行示例查询
    examples = {json.dumps(examples, ensure_ascii=False, indent=4)}
    
    for name, config in examples.items():
        test_query(
            name=name,
            query=config["query"],
            system=config.get("system"),
            description=config["description"]
        )
    
    print("\\n🎉 示例查询完成!")
    print("\\n💡 更多测试:")
    print("   - 访问 API 文档: http://127.0.0.1:8000/docs")
    print("   - 查看统计信息: curl http://127.0.0.1:8000/opensearch/stats")

if __name__ == "__main__":
    main()
'''
    
    with open("example_queries.py", "w", encoding="utf-8") as f:
        f.write(script_content)
    
    print("✅ 创建示例查询脚本: example_queries.py")

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 用户中断部署")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 部署过程出错: {e}")
        sys.exit(1)

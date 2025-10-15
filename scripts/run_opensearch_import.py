#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行 OpenSearch 数据导入的主脚本
"""

import sys
import os

def main():
    """主函数"""
    print("🚀 OpenSearch 数据导入流程")
    print("=" * 50)
    
    # 1. 首先清除现有索引（可选）
    print("1. 是否要清除现有索引？")
    clear_choice = input("   输入 'y' 清除现有数据，或按回车跳过: ").strip().lower()
    
    if clear_choice == 'y':
        print("🗑️  清除现有索引...")
        os.system("python quick_clear_index.py")
    
    # 2. 导入数据
    print("\n2. 🚀 开始导入数据...")
    print("   使用保留字段的导入脚本...")
    
    result = os.system("python import_to_opensearch_preserve_fields.py")
    
    if result == 0:
        print("\n✅ 数据导入成功!")
        
        # 3. 测试搜索功能
        print("\n3. 🧪 测试搜索功能...")
        test_choice = input("   是否要运行搜索测试？(y/N): ").strip().lower()
        
        if test_choice == 'y':
            os.system("python test_opensearch.py")
        
        print("\n🎉 OpenSearch 导入流程完成!")
        print("\n💡 接下来可以:")
        print("   - 启动 FastAPI 服务: cd .. && python -m app.main")
        print("   - 访问 API 文档: http://127.0.0.1:8000/docs")
        print("   - 测试故障匹配: curl 'http://127.0.0.1:8000/opensearch/match?q=发动机无法启动'")
        
    else:
        print("\n❌ 数据导入失败!")
        print("请检查 OpenSearch 连接和配置")

if __name__ == "__main__":
    main()

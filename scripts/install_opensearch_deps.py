#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安装 OpenSearch 相关依赖
"""

import subprocess
import sys
import os

def install_package(package):
    """安装Python包"""
    try:
        print(f"📦 安装 {package}...")
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', package
        ], check=True, capture_output=True, text=True)
        print(f"✅ {package} 安装成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {package} 安装失败: {e}")
        print(f"错误输出: {e.stderr}")
        return False

def main():
    """主函数"""
    print("🔧 安装 OpenSearch 相关依赖")
    print("=" * 40)
    
    # 需要安装的包
    packages = [
        'opensearch-py',  # OpenSearch Python 客户端
        'requests',       # HTTP 请求库
        'urllib3',        # HTTP 库
    ]
    
    success_count = 0
    
    for package in packages:
        if install_package(package):
            success_count += 1
    
    print(f"\n📊 安装结果: {success_count}/{len(packages)} 成功")
    
    if success_count == len(packages):
        print("🎉 所有依赖安装成功!")
        
        # 测试导入
        print("\n🧪 测试导入...")
        try:
            from opensearchpy import OpenSearch
            print("✅ opensearch-py 导入成功")
            
            import requests
            print("✅ requests 导入成功")
            
            print("\n✨ 依赖检查完成，可以开始导入数据!")
            return True
        except ImportError as e:
            print(f"❌ 导入测试失败: {e}")
            return False
    else:
        print("❌ 部分依赖安装失败，请检查网络连接或权限")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

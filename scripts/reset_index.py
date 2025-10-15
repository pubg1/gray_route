#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重置 OpenSearch 索引脚本 - 删除并重建索引
"""

import sys
import logging
from opensearchpy import OpenSearch
from opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def reset_index():
    """重置索引 - 删除并重建"""
    try:
        # 连接 OpenSearch
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
        
        index_name = INDEX_CONFIG['name']
        
        print(f"🔄 重置索引: {index_name}")
        print("=" * 40)
        
        # 1. 检查索引是否存在
        if client.indices.exists(index=index_name):
            # 获取当前索引信息
            stats = client.indices.stats(index=index_name)
            doc_count = stats['indices'][index_name]['total']['docs']['count']
            print(f"📊 当前文档数量: {doc_count:,}")
            
            # 删除索引
            print("🗑️  删除现有索引...")
            client.indices.delete(index=index_name)
            print("✅ 索引删除成功")
        else:
            print("ℹ️  索引不存在，将创建新索引")
        
        # 2. 重建索引
        print("🏗️  重建索引...")
        
        # 定义索引映射
        index_mapping = {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "vehicletype": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword"}}
                    },
                    "discussion": {"type": "text"},
                    "symptoms": {"type": "text"},
                    "solution": {"type": "text"},
                    "search_content": {"type": "text"},
                    "search_num": {"type": "integer"},
                    "rate": {"type": "float"},
                    "vin": {"type": "keyword"},
                    "created_at": {"type": "date"},
                    "source_index": {"type": "keyword"},
                    "source_type": {"type": "keyword"}
                }
            }
        }
        
        # 创建索引
        response = client.indices.create(index=index_name, body=index_mapping)
        
        if response.get('acknowledged', False):
            print("✅ 索引重建成功")
            
            # 验证索引状态
            health = client.cluster.health(index=index_name, wait_for_status='yellow', timeout='30s')
            print(f"📊 索引状态: {health['status']}")
            print(f"📊 分片数量: {health['active_shards']}")
            
            print("\n🎉 索引重置完成!")
            print(f"💡 现在可以重新导入数据: python run_import.py")
            return True
        else:
            print("❌ 索引重建失败")
            return False
            
    except Exception as e:
        logger.error(f"重置索引失败: {e}")
        return False

def main():
    """主函数"""
    print("🔄 OpenSearch 索引重置工具")
    print("=" * 50)
    
    print(f"📋 配置信息:")
    print(f"   主机: {OPENSEARCH_CONFIG['host']}")
    print(f"   索引: {INDEX_CONFIG['name']}")
    print()
    
    print("⚠️  警告: 此操作将完全删除并重建索引!")
    print("   - 所有现有数据将被永久删除")
    print("   - 索引结构将被重置为默认配置")
    print()
    
    confirm = input("确认要重置索引吗？(yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("👋 操作已取消")
        return False
    
    return reset_index()

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
        sys.exit(1)

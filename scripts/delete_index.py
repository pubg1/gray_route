#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接删除 OpenSearch 索引脚本
"""

import sys
from opensearchpy import OpenSearch
from opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG

def delete_index():
    """直接删除索引"""
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
        
        print(f"🗑️  删除索引: {index_name}")
        
        # 检查索引是否存在
        if not client.indices.exists(index=index_name):
            print("ℹ️  索引不存在")
            return True
        
        # 获取索引信息
        stats = client.indices.stats(index=index_name)
        doc_count = stats['indices'][index_name]['total']['docs']['count']
        size_bytes = stats['indices'][index_name]['total']['store']['size_in_bytes']
        size_mb = size_bytes / (1024 * 1024)
        
        print(f"📊 索引信息:")
        print(f"   文档数量: {doc_count:,}")
        print(f"   索引大小: {size_mb:.2f} MB")
        
        # 删除索引
        print("🚀 开始删除索引...")
        response = client.indices.delete(index=index_name)
        
        if response.get('acknowledged', False):
            print("✅ 索引删除成功")
            return True
        else:
            print("❌ 索引删除失败")
            return False
            
    except Exception as e:
        print(f"❌ 删除失败: {e}")
        return False

if __name__ == "__main__":
    print("🗑️  OpenSearch 索引删除工具")
    print("=" * 40)
    print(f"目标索引: {INDEX_CONFIG['name']}")
    print()
    
    success = delete_index()
    
    if success:
        print("\n🎉 索引删除完成!")
    else:
        print("\n❌ 索引删除失败!")
    
    sys.exit(0 if success else 1)

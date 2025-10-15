#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速清除 OpenSearch 索引数据脚本
"""

import sys
from opensearchpy import OpenSearch
from opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG

def quick_clear():
    """快速清除索引数据"""
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
        
        print(f"🗑️  快速清除索引: {index_name}")
        
        # 检查索引是否存在
        if not client.indices.exists(index=index_name):
            print("ℹ️  索引不存在")
            return True
        
        # 获取文档数量
        count_before = client.count(index=index_name)['count']
        print(f"📊 清除前文档数量: {count_before:,}")
        
        if count_before == 0:
            print("ℹ️  索引已为空")
            return True
        
        # 删除所有文档
        print("🚀 开始清除数据...")
        response = client.delete_by_query(
            index=index_name,
            body={"query": {"match_all": {}}},
            wait_for_completion=True,
            refresh=True
        )
        
        deleted_count = response.get('deleted', 0)
        print(f"✅ 成功删除 {deleted_count:,} 个文档")
        
        # 验证结果
        count_after = client.count(index=index_name)['count']
        print(f"📊 清除后文档数量: {count_after:,}")
        
        if count_after == 0:
            print("🎉 索引数据清除完成!")
            return True
        else:
            print(f"⚠️  仍有 {count_after} 个文档未删除")
            return False
            
    except Exception as e:
        print(f"❌ 清除失败: {e}")
        return False

if __name__ == "__main__":
    success = quick_clear()
    sys.exit(0 if success else 1)

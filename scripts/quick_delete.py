#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速删除索引 - 无确认
"""

from opensearchpy import OpenSearch
from opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG

# 连接并删除
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

try:
    if client.indices.exists(index=index_name):
        client.indices.delete(index=index_name)
        print(f"✅ 索引 '{index_name}' 已删除")
    else:
        print(f"ℹ️  索引 '{index_name}' 不存在")
except Exception as e:
    print(f"❌ 删除失败: {e}")

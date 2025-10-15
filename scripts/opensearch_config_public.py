#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenSearch 公网端点配置文件
"""

# OpenSearch 连接配置 (公网端点)
OPENSEARCH_CONFIG = {
    # 如果有公网端点，格式类似：
    # 'host': 'search-carbobo-xxxxx.us-east-1.es.amazonaws.com',
    'host': 'search-carbobo-xxxxx.us-east-1.es.amazonaws.com',  # 替换为实际的公网端点
    'port': 443,
    'username': "chebaobao",
    'password': "Chebaobao*88",
    'use_ssl': True,
    'verify_certs': True,
    'ssl_assert_hostname': False,
    'ssl_show_warn': False,
    'timeout': 30,
}

# 索引配置
INDEX_CONFIG = {
    'name': 'automotive_cases',
    'shards': 1,
    'replicas': 0,
}

# 导入配置
IMPORT_CONFIG = {
    'batch_size': 100,
    'timeout': 60,
}

# 数据文件路径
DATA_FILE = '../data/servicingcase_last.json'

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenSearch SSH 隧道配置文件
使用前需要先建立 SSH 隧道：
ssh -i your-key.pem -L 9200:vpc-endpoint:443 ubuntu@ec2-ip
"""

# OpenSearch 连接配置 (通过 SSH 隧道)
OPENSEARCH_CONFIG = {
    'host': 'localhost',  # 通过隧道连接本地端口
    'port': 9200,         # 本地隧道端口
    'username': "chebaobao",
    'password': "Chebaobao*88",
    'use_ssl': True,      # VPC 端点需要 SSL
    'verify_certs': False,  # 通过隧道时可能需要关闭证书验证
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

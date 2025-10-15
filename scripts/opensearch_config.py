#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenSearch 配置文件
"""

# OpenSearch 连接配置 (AWS VPC 端点)
OPENSEARCH_CONFIG = {
    'host': 'vpc-carbobo-hty6sxiqn2a5x4dbbiqjtj5reu.us-east-1.es.amazonaws.com',
    'port': 443,  # AWS OpenSearch VPC 端点使用 443 端口
    'username': "chebaobao",  # 如果需要认证，请填写用户名
    'password': "Chebaobao*88",  # 如果需要认证，请填写密码
    'use_ssl': True,  # VPC 端点必须使用 SSL
    'verify_certs': True,  # 建议验证证书
    'ssl_assert_hostname': False,  # VPC 端点可能需要关闭主机名验证
    'ssl_show_warn': False,  # 关闭 SSL 警告
    'timeout': 30,  # 连接超时时间
}

# 索引配置
INDEX_CONFIG = {
    'name': 'automotive_cases',  # 索引名称
    'shards': 1,  # 分片数
    'replicas': 0,  # 副本数
}

# 导入配置
IMPORT_CONFIG = {
    'batch_size': 100,  # 批量导入大小
    'timeout': 60,  # 请求超时时间（秒）
}

# 数据文件路径
DATA_FILE = '../data/servicingcase_last.json'

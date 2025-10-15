#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速验证所有原有字段是否完整保留
"""

import json
import sys
from opensearchpy import OpenSearch
from opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG

def main():
    """快速验证"""
    print("🔍 快速验证所有原有字段保留情况")
    
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
            timeout=10
        )
        
        # 获取样本文档
        response = client.search(
            index=INDEX_CONFIG['name'],
            body={"query": {"match_all": {}}, "size": 1}
        )
        
        if not response['hits']['hits']:
            print("❌ 没有找到文档")
            return False
        
        doc = response['hits']['hits'][0]
        source = doc['_source']
        
        print(f"📋 样本文档 ID: {doc['_id']}")
        print(f"📊 总字段数: {len(source)}")
        
        # 检查关键原有字段
        original_fields = [
            'vehicletype', 'searchNum', 'discussion', 'search', 'solution', 
            'rate', 'vin', 'id', 'createtime', 'faultcode', 'creatorid',
            'spare1', 'spare2', 'spare15', 'egon', 'symptoms', 'money',
            'vehiclebrand', 'topic', 'searchContent'
        ]
        
        present_count = 0
        for field in original_fields:
            if field in source:
                present_count += 1
                print(f"✅ {field}")
            else:
                print(f"❌ {field} - 缺失")
        
        # 检查新增字段
        new_fields = ['text', 'system', 'part', 'tags', 'popularity']
        new_count = 0
        for field in new_fields:
            if field in source:
                new_count += 1
                print(f"✨ {field}")
        
        # 结果
        original_rate = present_count / len(original_fields)
        new_rate = new_count / len(new_fields)
        
        print(f"\n📊 结果:")
        print(f"   原有字段: {present_count}/{len(original_fields)} ({original_rate:.1%})")
        print(f"   新增字段: {new_count}/{len(new_fields)} ({new_rate:.1%})")
        print(f"   总字段数: {len(source)}")
        
        if original_rate >= 0.9 and new_rate >= 0.8:
            print("🎉 字段保留验证通过!")
            return True
        else:
            print("⚠️  字段保留不完整")
            return False
            
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

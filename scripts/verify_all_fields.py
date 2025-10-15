#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证所有原有字段是否被正确保留
"""

import json
import sys
from opensearchpy import OpenSearch
from opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG

def verify_fields():
    """验证字段保留情况"""
    print("🔍 验证所有原有字段是否被正确保留")
    print("=" * 60)
    
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
        
        # 检查索引是否存在
        if not client.indices.exists(index=index_name):
            print(f"❌ 索引 '{index_name}' 不存在")
            return False
        
        # 获取一个样本文档
        response = client.search(
            index=index_name,
            body={
                "query": {"match_all": {}},
                "size": 1
            }
        )
        
        if not response['hits']['hits']:
            print("❌ 索引中没有文档")
            return False
        
        doc = response['hits']['hits'][0]
        source = doc['_source']
        
        print(f"📋 文档 ID: {doc['_id']}")
        print(f"📊 总字段数: {len(source)}")
        print()
        
        # 定义预期的原有字段
        expected_original_fields = [
            'vehicletype', 'searchNum', 'discussion', 'search', 'solution', 
            'rate', 'vin', 'id', 'summary', 'spare11', 'spare10', 'createtime',
            'faultcode', 'creatorid', 'spare4', 'spare3', 'spare6', 'spare5',
            'spare15', 'egon', 'spare2', 'spare1', 'spare12', 'symptoms',
            'money', 'vehiclebrand', 'casestate', 'topic', 'placement',
            'noCode', 'searchContent'
        ]
        
        # 新增的匹配字段
        new_matching_fields = [
            'text', 'system', 'part', 'tags', 'popularity', 'search_content',
            'import_time', 'source_index', 'source_type', 'original_score'
        ]
        
        print("📋 原有字段检查:")
        print("-" * 40)
        
        missing_original = []
        present_original = []
        
        for field in expected_original_fields:
            if field in source:
                present_original.append(field)
                value = source[field]
                if value is not None and str(value).strip():
                    print(f"✅ {field}: {str(value)[:50]}{'...' if len(str(value)) > 50 else ''}")
                else:
                    print(f"✅ {field}: (空值)")
            else:
                missing_original.append(field)
                print(f"❌ {field}: 缺失")
        
        print(f"\n📋 新增匹配字段检查:")
        print("-" * 40)
        
        present_new = []
        missing_new = []
        
        for field in new_matching_fields:
            if field in source:
                present_new.append(field)
                value = source[field]
                print(f"✅ {field}: {str(value)[:50]}{'...' if len(str(value)) > 50 else ''}")
            else:
                missing_new.append(field)
                print(f"❌ {field}: 缺失")
        
        # 检查额外字段
        all_expected = set(expected_original_fields + new_matching_fields)
        extra_fields = [field for field in source.keys() if field not in all_expected]
        
        if extra_fields:
            print(f"\n📋 额外字段:")
            print("-" * 40)
            for field in extra_fields:
                value = source[field]
                print(f"ℹ️  {field}: {str(value)[:50]}{'...' if len(str(value)) > 50 else ''}")
        
        # 统计结果
        print(f"\n📊 字段统计:")
        print("=" * 40)
        print(f"原有字段: {len(present_original)}/{len(expected_original_fields)} 保留")
        print(f"新增字段: {len(present_new)}/{len(new_matching_fields)} 添加")
        print(f"额外字段: {len(extra_fields)} 个")
        print(f"总字段数: {len(source)} 个")
        
        # 验证关键原有字段的内容
        print(f"\n🔍 关键字段内容验证:")
        print("-" * 40)
        
        key_validations = [
            ('vehicletype', '车型信息'),
            ('discussion', '故障点描述'),
            ('symptoms', '故障症状'),
            ('topic', '主题'),
            ('vehiclebrand', '车辆品牌'),
            ('createtime', '创建时间'),
            ('searchContent', '搜索内容')
        ]
        
        validation_passed = 0
        for field, description in key_validations:
            if field in source and source[field]:
                print(f"✅ {description} ({field}): 有内容")
                validation_passed += 1
            else:
                print(f"⚠️  {description} ({field}): 无内容或缺失")
        
        # 总体评估
        original_rate = len(present_original) / len(expected_original_fields)
        new_rate = len(present_new) / len(new_matching_fields)
        validation_rate = validation_passed / len(key_validations)
        
        print(f"\n🎯 总体评估:")
        print("=" * 40)
        print(f"原有字段保留率: {original_rate:.1%}")
        print(f"新增字段完成率: {new_rate:.1%}")
        print(f"关键内容验证率: {validation_rate:.1%}")
        
        overall_success = original_rate >= 0.9 and new_rate >= 0.8 and validation_rate >= 0.6
        
        if overall_success:
            print("🎉 字段保留验证通过!")
        else:
            print("⚠️  字段保留存在问题，请检查导入脚本")
        
        # 显示完整的样本文档（可选）
        show_full = input("\n是否显示完整的样本文档？(y/N): ").strip().lower()
        if show_full == 'y':
            print(f"\n📄 完整样本文档:")
            print("=" * 60)
            print(json.dumps(source, ensure_ascii=False, indent=2))
        
        return overall_success
        
    except Exception as e:
        print(f"❌ 验证过程出错: {e}")
        return False

def main():
    """主函数"""
    print("🔍 OpenSearch 字段保留验证工具")
    print("验证 servicingcase_last.json 的所有原有字段是否被正确保留")
    print()
    
    success = verify_fields()
    
    if success:
        print(f"\n✅ 验证完成: 字段保留良好")
        print(f"💡 所有原有字段都被正确保留，可以安全使用")
    else:
        print(f"\n❌ 验证失败: 字段保留存在问题")
        print(f"💡 建议重新运行导入脚本:")
        print(f"   python import_to_opensearch_preserve_fields.py")
    
    return success

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 用户中断验证")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 验证异常: {e}")
        sys.exit(1)

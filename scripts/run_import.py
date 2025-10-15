#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的 OpenSearch 数据导入脚本
"""

import os
import sys
import logging
from opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG, IMPORT_CONFIG, DATA_FILE

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from import_to_opensearch import OpenSearchImporter

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """主函数"""
    print("🚀 开始导入汽车维修案例数据到 OpenSearch")
    print("=" * 60)
    
    # 检查数据文件是否存在
    data_file_path = os.path.join(os.path.dirname(__file__), DATA_FILE)
    if not os.path.exists(data_file_path):
        logger.error(f"数据文件不存在: {data_file_path}")
        return False
    
    logger.info(f"数据文件: {data_file_path}")
    logger.info(f"目标索引: {INDEX_CONFIG['name']}")
    logger.info(f"OpenSearch: {OPENSEARCH_CONFIG['host']}:{OPENSEARCH_CONFIG['port']}")
    
    try:
        # 创建导入器
        importer = OpenSearchImporter(
            host=OPENSEARCH_CONFIG['host'],
            port=OPENSEARCH_CONFIG['port'],
            username=OPENSEARCH_CONFIG['username'],
            password=OPENSEARCH_CONFIG['password'],
            use_ssl=OPENSEARCH_CONFIG['use_ssl'],
            verify_certs=OPENSEARCH_CONFIG['verify_certs'],
            ssl_assert_hostname=OPENSEARCH_CONFIG.get('ssl_assert_hostname', False),
            ssl_show_warn=OPENSEARCH_CONFIG.get('ssl_show_warn', False),
            timeout=OPENSEARCH_CONFIG.get('timeout', 30)
        )
        
        # 导入数据
        success = importer.import_data(
            json_file=data_file_path,
            index_name=INDEX_CONFIG['name'],
            batch_size=IMPORT_CONFIG['batch_size']
        )
        
        if success:
            print("\n🎉 数据导入成功!")
            
            # 进行搜索测试
            print("\n🔍 进行搜索测试...")
            test_queries = ["发动机", "刹车", "变速箱", "空调"]
            for query in test_queries:
                print(f"\n测试查询: {query}")
                importer.search_test(INDEX_CONFIG['name'], query)
            
            print(f"\n✅ 导入完成! 索引名称: {INDEX_CONFIG['name']}")
            return True
        else:
            print("\n❌ 数据导入失败!")
            return False
            
    except Exception as e:
        logger.error(f"导入过程出错: {e}")
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 用户中断操作")
        sys.exit(1)

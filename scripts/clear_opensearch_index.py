#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清除 OpenSearch 索引数据脚本
"""

import sys
import logging
from opensearchpy import OpenSearch
from opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OpenSearchCleaner:
    def __init__(self):
        """初始化 OpenSearch 连接"""
        try:
            # 创建 OpenSearch 客户端
            self.client = OpenSearch(
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
            
            # 测试连接
            info = self.client.info()
            logger.info(f"成功连接到 OpenSearch: {info['version']['number']}")
            
        except Exception as e:
            logger.error(f"连接 OpenSearch 失败: {e}")
            raise

    def check_index_exists(self, index_name: str):
        """检查索引是否存在"""
        try:
            exists = self.client.indices.exists(index=index_name)
            if exists:
                # 获取索引信息
                stats = self.client.indices.stats(index=index_name)
                doc_count = stats['indices'][index_name]['total']['docs']['count']
                size_bytes = stats['indices'][index_name]['total']['store']['size_in_bytes']
                size_mb = size_bytes / (1024 * 1024)
                
                logger.info(f"索引 '{index_name}' 存在")
                logger.info(f"  文档数量: {doc_count:,}")
                logger.info(f"  索引大小: {size_mb:.2f} MB")
                return True, doc_count, size_mb
            else:
                logger.warning(f"索引 '{index_name}' 不存在")
                return False, 0, 0
        except Exception as e:
            logger.error(f"检查索引失败: {e}")
            return False, 0, 0

    def clear_index_data(self, index_name: str, method: str = 'delete_by_query'):
        """清除索引数据
        
        Args:
            index_name: 索引名称
            method: 清除方法
                - 'delete_by_query': 删除所有文档，保留索引结构
                - 'delete_index': 删除整个索引
                - 'truncate': 先删除索引再重建（如果有映射的话）
        """
        
        if method == 'delete_by_query':
            return self._delete_all_documents(index_name)
        elif method == 'delete_index':
            return self._delete_entire_index(index_name)
        elif method == 'truncate':
            return self._truncate_index(index_name)
        else:
            logger.error(f"不支持的清除方法: {method}")
            return False

    def _delete_all_documents(self, index_name: str):
        """删除所有文档，保留索引结构"""
        try:
            logger.info(f"开始删除索引 '{index_name}' 中的所有文档...")
            
            # 使用 delete_by_query 删除所有文档
            response = self.client.delete_by_query(
                index=index_name,
                body={
                    "query": {
                        "match_all": {}
                    }
                },
                wait_for_completion=True,
                refresh=True
            )
            
            deleted_count = response.get('deleted', 0)
            took_ms = response.get('took', 0)
            
            logger.info(f"✅ 成功删除 {deleted_count:,} 个文档")
            logger.info(f"   耗时: {took_ms} ms")
            
            # 验证删除结果
            remaining_count = self.client.count(index=index_name)['count']
            if remaining_count == 0:
                logger.info("✅ 索引数据清除完成，索引结构保留")
                return True
            else:
                logger.warning(f"⚠️  仍有 {remaining_count} 个文档未删除")
                return False
                
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            return False

    def _delete_entire_index(self, index_name: str):
        """删除整个索引"""
        try:
            logger.info(f"开始删除整个索引 '{index_name}'...")
            
            response = self.client.indices.delete(index=index_name)
            
            if response.get('acknowledged', False):
                logger.info("✅ 索引删除成功")
                return True
            else:
                logger.error("❌ 索引删除失败")
                return False
                
        except Exception as e:
            logger.error(f"删除索引失败: {e}")
            return False

    def _truncate_index(self, index_name: str):
        """截断索引（删除后重建）"""
        try:
            logger.info(f"开始截断索引 '{index_name}'...")
            
            # 1. 获取当前索引的映射和设置
            try:
                mapping_response = self.client.indices.get_mapping(index=index_name)
                settings_response = self.client.indices.get_settings(index=index_name)
                
                current_mapping = mapping_response[index_name]['mappings']
                current_settings = settings_response[index_name]['settings']['index']
                
                # 清理设置中的系统字段
                clean_settings = {}
                for key, value in current_settings.items():
                    if not key.startswith(('uuid', 'version', 'creation_date', 'provided_name')):
                        clean_settings[key] = value
                
                logger.info("✅ 已保存索引映射和设置")
                
            except Exception as e:
                logger.warning(f"获取索引映射失败，将使用默认配置: {e}")
                current_mapping = None
                clean_settings = {}
            
            # 2. 删除索引
            if not self._delete_entire_index(index_name):
                return False
            
            # 3. 重建索引
            if current_mapping:
                index_body = {
                    "mappings": current_mapping,
                    "settings": clean_settings
                }
            else:
                # 使用基本映射
                index_body = {
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
                            "created_at": {"type": "date"}
                        }
                    }
                }
            
            response = self.client.indices.create(index=index_name, body=index_body)
            
            if response.get('acknowledged', False):
                logger.info("✅ 索引重建成功")
                return True
            else:
                logger.error("❌ 索引重建失败")
                return False
                
        except Exception as e:
            logger.error(f"截断索引失败: {e}")
            return False

def main():
    """主函数"""
    print("🗑️  OpenSearch 索引数据清除工具")
    print("=" * 50)
    
    # 显示配置信息
    print(f"📋 连接配置:")
    print(f"   主机: {OPENSEARCH_CONFIG['host']}")
    print(f"   端口: {OPENSEARCH_CONFIG['port']}")
    print(f"   索引: {INDEX_CONFIG['name']}")
    print()
    
    try:
        # 创建清理器
        cleaner = OpenSearchCleaner()
        
        # 检查索引
        index_name = INDEX_CONFIG['name']
        exists, doc_count, size_mb = cleaner.check_index_exists(index_name)
        
        if not exists:
            print("ℹ️  索引不存在，无需清除")
            return True
        
        if doc_count == 0:
            print("ℹ️  索引已为空，无需清除")
            return True
        
        # 确认操作
        print(f"\n⚠️  警告: 即将清除索引 '{index_name}' 的数据")
        print(f"   文档数量: {doc_count:,}")
        print(f"   索引大小: {size_mb:.2f} MB")
        print()
        print("清除方法:")
        print("  1. delete_by_query - 删除所有文档，保留索引结构")
        print("  2. delete_index    - 删除整个索引")
        print("  3. truncate        - 删除索引后重建")
        print()
        
        # 获取用户选择
        while True:
            choice = input("请选择清除方法 (1/2/3) 或输入 'q' 取消: ").strip().lower()
            
            if choice == 'q':
                print("👋 操作已取消")
                return False
            elif choice == '1':
                method = 'delete_by_query'
                break
            elif choice == '2':
                method = 'delete_index'
                break
            elif choice == '3':
                method = 'truncate'
                break
            else:
                print("❌ 无效选择，请输入 1、2、3 或 q")
        
        # 最终确认
        confirm = input(f"\n🚨 确认要使用 '{method}' 方法清除数据吗？(yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("👋 操作已取消")
            return False
        
        # 执行清除
        print(f"\n🚀 开始执行清除操作...")
        success = cleaner.clear_index_data(index_name, method)
        
        if success:
            print("\n🎉 索引数据清除成功!")
            
            # 显示清除后的状态
            if method != 'delete_index':
                exists, new_doc_count, new_size_mb = cleaner.check_index_exists(index_name)
                if exists:
                    print(f"   当前文档数量: {new_doc_count:,}")
                    print(f"   当前索引大小: {new_size_mb:.2f} MB")
            
            return True
        else:
            print("\n❌ 索引数据清除失败!")
            return False
            
    except Exception as e:
        logger.error(f"清除过程出错: {e}")
        return False

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

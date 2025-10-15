#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 servicingcase_last.json 数据导入 OpenSearch
"""

import json
import re
from typing import Dict, List, Any, Optional
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk
import argparse
import sys
from datetime import datetime
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OpenSearchImporter:
    def __init__(self, host: str = 'localhost', port: int = 9200, 
                 username: str = None, password: str = None, 
                 use_ssl: bool = False, verify_certs: bool = False,
                 ssl_assert_hostname: bool = True, ssl_show_warn: bool = True,
                 timeout: int = 30):
        """初始化 OpenSearch 连接"""
        
        # 处理 AWS VPC 端点 URL
        if host.startswith('http://') or host.startswith('https://'):
            host = host.replace('https://', '').replace('http://', '')
        
        # OpenSearch 连接配置
        self.config = {
            'hosts': [{'host': host, 'port': port}],
            'http_compress': True,
            'use_ssl': use_ssl,
            'verify_certs': verify_certs,
            'ssl_assert_hostname': ssl_assert_hostname,
            'ssl_show_warn': ssl_show_warn,
            'timeout': timeout,
            'max_retries': 3,
            'retry_on_timeout': True,
        }
        
        # 如果提供了认证信息
        if username and password:
            self.config['http_auth'] = (username, password)
        
        try:
            self.client = OpenSearch(**self.config)
            # 测试连接
            info = self.client.info()
            logger.info(f"成功连接到 OpenSearch: {info['version']['number']}")
        except Exception as e:
            logger.error(f"连接 OpenSearch 失败: {e}")
            raise
    
    def clean_html_content(self, text: str) -> str:
        """清理HTML内容"""
        if not text:
            return ""
        
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text)
        # 移除首尾空白
        text = text.strip()
        
        return text
    
    def extract_symptoms_and_solution(self, search_content: str) -> Dict[str, str]:
        """从search内容中提取故障现象和解决方案"""
        if not search_content:
            return {"symptoms": "", "solution": ""}
        
        # 清理HTML
        clean_content = self.clean_html_content(search_content)
        
        # 尝试提取故障现象（通常在开头）
        symptoms = ""
        solution = ""
        
        # 按句号分割，取前几句作为故障现象
        sentences = clean_content.split('。')
        if sentences:
            # 取前2-3句作为故障现象
            symptoms = '。'.join(sentences[:3]).strip()
            if symptoms and not symptoms.endswith('。'):
                symptoms += '。'
        
        # 查找解决方案关键词
        solution_keywords = ['更换', '维修', '解决', '处理', '修复', '故障排除']
        for sentence in sentences:
            if any(keyword in sentence for keyword in solution_keywords):
                solution = sentence.strip()
                break
        
        return {
            "symptoms": symptoms[:500] if symptoms else "",  # 限制长度
            "solution": solution[:300] if solution else ""   # 限制长度
        }
    
    def transform_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """转换单条记录格式"""
        source = record.get('_source', {})
        
        # 提取故障现象和解决方案
        search_content = source.get('search', '')
        extracted = self.extract_symptoms_and_solution(search_content)
        
        # 构建新的文档结构
        transformed = {
            'id': record.get('_id', ''),
            'vehicletype': source.get('vehicletype', ''),
            'discussion': source.get('discussion', ''),
            'symptoms': extracted['symptoms'],
            'solution': extracted['solution'],
            'search_content': self.clean_html_content(search_content)[:2000],  # 限制长度
            'search_num': source.get('searchNum', 0),
            'rate': source.get('rate'),
            'vin': source.get('vin'),
            'created_at': datetime.now().isoformat(),
            'source_index': record.get('_index', ''),
            'source_type': record.get('_type', '')
        }
        
        # 移除空值
        return {k: v for k, v in transformed.items() if v is not None and v != ''}
    
    def create_index_mapping(self, index_name: str):
        """创建索引映射 - 使用简化配置避免AWS限制"""
        try:
            if self.client.indices.exists(index=index_name):
                logger.info(f"索引 {index_name} 已存在")
                return True
            
            # 使用最简单的配置，让AWS OpenSearch自动处理分片和副本
            simple_mapping = {
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
                        "rate": {"type": "float"},
                        "vin": {"type": "keyword"},
                        "created_at": {"type": "date"},
                        "source_index": {"type": "keyword"},
                        "source_type": {"type": "keyword"}
                    }
                }
                # 不设置 settings，让 AWS OpenSearch 使用默认配置
            }
            
            response = self.client.indices.create(index=index_name, body=simple_mapping)
            logger.info(f"成功创建索引: {index_name}")
            return True
        except Exception as e:
            logger.error(f"创建索引失败: {e}")
            # 如果创建索引失败，尝试不创建索引，直接导入数据（让OpenSearch自动创建）
            logger.info("尝试跳过索引创建，直接导入数据...")
            return True  # 返回True继续执行
    
    def import_data(self, json_file: str, index_name: str, batch_size: int = 100):
        """导入数据到 OpenSearch"""
        
        # 创建索引
        if not self.create_index_mapping(index_name):
            return False
        
        try:
            # 读取JSON文件
            logger.info(f"读取文件: {json_file}")
            with open(json_file, 'r', encoding='utf-8') as f:
                data = []
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        record = json.loads(line)
                        data.append(record)
                    except json.JSONDecodeError as e:
                        logger.warning(f"第 {line_num} 行JSON解析失败: {e}")
                        continue
            
            logger.info(f"成功读取 {len(data)} 条记录")
            
            # 转换数据格式
            logger.info("转换数据格式...")
            documents = []
            for record in data:
                try:
                    transformed = self.transform_record(record)
                    if transformed:
                        # 构建bulk操作格式
                        doc = {
                            "_index": index_name,
                            "_id": transformed.get('id'),
                            "_source": transformed
                        }
                        documents.append(doc)
                except Exception as e:
                    logger.warning(f"转换记录失败: {e}")
                    continue
            
            logger.info(f"成功转换 {len(documents)} 条记录")
            
            # 批量导入
            logger.info("开始批量导入...")
            success_count = 0
            error_count = 0
            
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]
                try:
                    success, failed = bulk(
                        self.client,
                        batch,
                        index=index_name,
                        chunk_size=batch_size,
                        request_timeout=60
                    )
                    success_count += success
                    error_count += len(failed) if failed else 0
                    
                    logger.info(f"批次 {i//batch_size + 1}: 成功 {success} 条")
                    
                except Exception as e:
                    logger.error(f"批量导入失败: {e}")
                    error_count += len(batch)
            
            # 刷新索引
            self.client.indices.refresh(index=index_name)
            
            logger.info(f"导入完成! 成功: {success_count}, 失败: {error_count}")
            
            # 验证导入结果
            count_result = self.client.count(index=index_name)
            actual_count = count_result['count']
            logger.info(f"索引中实际文档数量: {actual_count}")
            
            return True
            
        except Exception as e:
            logger.error(f"导入过程出错: {e}")
            return False
    
    def search_test(self, index_name: str, query: str = "发动机"):
        """测试搜索功能"""
        try:
            search_body = {
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["symptoms^2", "discussion^1.5", "solution", "search_content"]
                    }
                },
                "size": 5
            }
            
            response = self.client.search(index=index_name, body=search_body)
            
            logger.info(f"搜索测试 '{query}' 结果:")
            for hit in response['hits']['hits']:
                source = hit['_source']
                logger.info(f"  ID: {source.get('id', 'N/A')}")
                logger.info(f"  车型: {source.get('vehicletype', 'N/A')}")
                logger.info(f"  故障: {source.get('discussion', 'N/A')}")
                logger.info(f"  评分: {hit['_score']}")
                logger.info("  ---")
                
        except Exception as e:
            logger.error(f"搜索测试失败: {e}")

def main():
    parser = argparse.ArgumentParser(description='导入汽车维修案例数据到 OpenSearch')
    parser.add_argument('--file', '-f', required=True, help='JSON文件路径')
    parser.add_argument('--index', '-i', default='automotive_cases', help='索引名称')
    parser.add_argument('--host', default='localhost', help='OpenSearch主机')
    parser.add_argument('--port', type=int, default=9200, help='OpenSearch端口')
    parser.add_argument('--username', '-u', help='用户名')
    parser.add_argument('--password', '-p', help='密码')
    parser.add_argument('--ssl', action='store_true', help='使用SSL')
    parser.add_argument('--batch-size', type=int, default=100, help='批量大小')
    parser.add_argument('--test', action='store_true', help='导入后进行搜索测试')
    
    args = parser.parse_args()
    
    try:
        # 创建导入器
        importer = OpenSearchImporter(
            host=args.host,
            port=args.port,
            username=args.username,
            password=args.password,
            use_ssl=args.ssl
        )
        
        # 导入数据
        success = importer.import_data(
            json_file=args.file,
            index_name=args.index,
            batch_size=args.batch_size
        )
        
        if success:
            logger.info("数据导入成功!")
            
            # 进行搜索测试
            if args.test:
                logger.info("进行搜索测试...")
                importer.search_test(args.index, "发动机")
                importer.search_test(args.index, "刹车")
        else:
            logger.error("数据导入失败!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("用户中断操作")
        sys.exit(1)
    except Exception as e:
        logger.error(f"程序执行出错: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

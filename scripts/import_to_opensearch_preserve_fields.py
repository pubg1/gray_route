#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
保留所有原有字段的 OpenSearch 导入脚本
按照 README.md 设计，保留 servicingcase_last.json 的所有字段，特别是不更改数据 ID
"""

import json
import sys
import os
import logging
import re
from datetime import datetime
from opensearchpy import OpenSearch
from opensearch_config import OPENSEARCH_CONFIG, INDEX_CONFIG, IMPORT_CONFIG

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OpenSearchImporterPreserveFields:
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

    def clean_html_content(self, html_content: str) -> str:
        """清理HTML内容，提取纯文本"""
        if not html_content:
            return ""
        
        # 移除HTML标签
        clean_text = re.sub(r'<[^>]+>', '', html_content)
        # 移除多余的空白字符
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        # 移除图片链接等无用信息
        clean_text = re.sub(r'https?://[^\s]+', '', clean_text)
        
        return clean_text

    def extract_phenomena_from_content(self, content: str, discussion: str) -> str:
        """从内容中提取故障现象"""
        if not content:
            return discussion or ""
        
        # 清理HTML内容
        clean_content = self.clean_html_content(content)
        
        # 尝试提取故障现象的关键信息
        # 通常在内容开头或包含特定关键词的部分
        phenomena_keywords = [
            "故障现象", "客户反映", "车主描述", "故障描述", 
            "症状", "问题", "异常", "故障", "不正常"
        ]
        
        sentences = clean_content.split('。')
        phenomena_sentences = []
        
        for sentence in sentences[:5]:  # 只取前5句
            sentence = sentence.strip()
            if len(sentence) > 10:  # 过滤太短的句子
                # 如果包含故障现象关键词，优先选择
                if any(keyword in sentence for keyword in phenomena_keywords):
                    phenomena_sentences.insert(0, sentence)
                else:
                    phenomena_sentences.append(sentence)
        
        # 组合故障现象，优先使用discussion
        if discussion:
            phenomena = discussion
            if phenomena_sentences:
                phenomena += " / " + " / ".join(phenomena_sentences[:2])
        else:
            phenomena = " / ".join(phenomena_sentences[:3]) if phenomena_sentences else ""
        
        return phenomena[:500]  # 限制长度

    def extract_system_and_part(self, content: str, discussion: str) -> tuple:
        """从内容中提取系统和部件信息"""
        full_text = f"{discussion} {self.clean_html_content(content)}"
        
        # 系统映射
        system_keywords = {
            "发动机": ["发动机", "引擎", "燃油", "点火", "进气", "排气", "冷却"],
            "变速箱/传动": ["变速器", "变速箱", "传动", "离合器", "差速器"],
            "制动": ["刹车", "制动", "ABS", "ESP", "制动踏板"],
            "转向": ["转向", "方向盘", "助力", "转向柱"],
            "悬挂": ["悬挂", "减震", "弹簧", "避震"],
            "电子电气": ["电池", "电路", "ECU", "传感器", "线束", "模块"],
            "空调": ["空调", "制冷", "暖风", "压缩机"],
            "车身": ["车门", "车窗", "座椅", "灯光", "仪表"],
            "其他": []
        }
        
        # 检测系统
        detected_system = "其他"
        for system, keywords in system_keywords.items():
            if any(keyword in full_text for keyword in keywords):
                detected_system = system
                break
        
        # 提取部件信息（通常在discussion中或内容开头）
        part_patterns = [
            r"([^，。]+(?:传感器|模块|控制器|开关|阀|泵|管|线束|插头|继电器))",
            r"([^，。]+(?:系统|装置|机构|总成))",
        ]
        
        detected_part = ""
        for pattern in part_patterns:
            matches = re.findall(pattern, full_text)
            if matches:
                detected_part = matches[0].strip()
                break
        
        if not detected_part and discussion:
            # 如果没有找到特定部件，使用discussion作为部件描述
            detected_part = discussion[:50]
        
        return detected_system, detected_part

    def extract_tags(self, vehicletype: str, content: str, discussion: str) -> list:
        """提取标签"""
        tags = []
        
        # 添加车型标签
        if vehicletype:
            tags.append(vehicletype)
        
        # 添加维修案例标签
        tags.append("维修案例")
        
        # 从内容中提取关键词作为标签
        full_text = f"{discussion} {self.clean_html_content(content)}"
        
        # 故障类型标签
        fault_keywords = {
            "启动故障": ["无法启动", "启动困难", "不着车"],
            "故障灯": ["故障灯", "警告灯", "报警"],
            "异响": ["异响", "噪音", "声音异常"],
            "漏油": ["漏油", "渗油", "油液泄漏"],
            "过热": ["过热", "温度高", "高温"],
            "振动": ["振动", "抖动", "不稳定"],
            "失效": ["失效", "不工作", "无效果"]
        }
        
        for tag, keywords in fault_keywords.items():
            if any(keyword in full_text for keyword in keywords):
                tags.append(tag)
        
        return list(set(tags))  # 去重

    def transform_record(self, record: dict) -> dict:
        """转换单条记录，保留所有原有字段"""
        source = record.get('_source', {})
        
        # 保留原有的所有字段（完整保留）
        transformed = {}
        
        # 直接复制所有原有字段
        for key, value in source.items():
            transformed[key] = value
        
        # 添加按照 README.md 设计的新字段，用于故障现象匹配
        phenomena_text = self.extract_phenomena_from_content(
            source.get('search', ''), 
            source.get('discussion', '')
        )
        
        system, part = self.extract_system_and_part(
            source.get('search', ''), 
            source.get('discussion', '')
        )
        
        tags = self.extract_tags(
            source.get('vehicletype', ''),
            source.get('search', ''),
            source.get('discussion', '')
        )
        
        # 按照 README.md 的 JSONL 格式添加字段（不覆盖原有字段）
        # 只添加新的匹配字段，如果原字段存在则不覆盖
        additional_fields = {
            # 故障现象匹配相关字段
            'text': phenomena_text,  # 主要的故障现象描述
            'system': system,        # 系统分类
            'part': part,           # 部件信息
            'tags': tags,           # 标签列表
            'popularity': source.get('searchNum', 0),  # 使用searchNum作为热度
            
            # 搜索相关字段
            'search_content': self.clean_html_content(source.get('search', '')),
            'import_time': datetime.now().isoformat(),
            
            # 原始数据标识
            'source_index': record.get('_index', ''),
            'source_type': record.get('_type', ''),
            'original_score': record.get('_score', 1)
        }
        
        # 只添加不存在的字段，避免覆盖原有数据
        for key, value in additional_fields.items():
            if key not in transformed:
                transformed[key] = value
        
        return transformed

    def create_index_mapping(self, index_name: str):
        """创建索引映射，支持故障现象匹配"""
        try:
            if self.client.indices.exists(index=index_name):
                logger.info(f"索引 {index_name} 已存在")
                return True
            
            # 按照 README.md 设计的索引映射，包含所有原有字段
            mapping = {
                "mappings": {
                    "properties": {
                        # 所有原有字段的映射
                        "vehicletype": {
                            "type": "text",
                            "fields": {"keyword": {"type": "keyword"}}
                        },
                        "searchNum": {"type": "integer"},
                        "discussion": {"type": "text"},
                        "search": {"type": "text"},
                        "solution": {"type": "text"},
                        "rate": {"type": "float"},
                        "vin": {"type": "keyword"},
                        "id": {"type": "keyword"},
                        "summary": {"type": "text"},
                        "spare11": {"type": "text"},
                        "spare10": {"type": "text"},
                        "createtime": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd||epoch_millis"},
                        "faultcode": {"type": "text"},
                        "creatorid": {"type": "keyword"},
                        "spare4": {"type": "text"},
                        "spare3": {"type": "text"},
                        "spare6": {"type": "text"},
                        "spare5": {"type": "text"},
                        "spare15": {"type": "text"},
                        "egon": {"type": "text"},
                        "spare2": {"type": "text"},
                        "spare1": {"type": "text"},
                        "spare12": {"type": "text"},
                        "symptoms": {"type": "text"},
                        "money": {"type": "text"},
                        "vehiclebrand": {
                            "type": "text",
                            "fields": {"keyword": {"type": "keyword"}}
                        },
                        "casestate": {"type": "keyword"},
                        "topic": {"type": "text"},
                        "placement": {"type": "text"},
                        "noCode": {"type": "text"},
                        "searchContent": {"type": "text"},
                        
                        # 故障现象匹配字段（按照 README.md 设计）
                        "text": {
                            "type": "text",
                            "analyzer": "standard"  # 主要的故障现象文本
                        },
                        "system": {
                            "type": "text",
                            "fields": {"keyword": {"type": "keyword"}}
                        },
                        "part": {
                            "type": "text",
                            "fields": {"keyword": {"type": "keyword"}}
                        },
                        "tags": {"type": "keyword"},
                        "popularity": {"type": "integer"},
                        
                        # 搜索辅助字段
                        "search_content": {"type": "text"},
                        "import_time": {"type": "date"},
                        
                        # 原始数据字段
                        "source_index": {"type": "keyword"},
                        "source_type": {"type": "keyword"},
                        "original_score": {"type": "float"}
                    }
                }
            }
            
            response = self.client.indices.create(index=index_name, body=mapping)
            logger.info(f"成功创建索引: {index_name}")
            return True
            
        except Exception as e:
            logger.error(f"创建索引失败: {e}")
            logger.info("尝试跳过索引创建，直接导入数据...")
            return True

    def import_data(self, json_file: str, index_name: str, batch_size: int = 100):
        """导入数据到 OpenSearch，保留原有ID"""
        
        # 创建索引
        if not self.create_index_mapping(index_name):
            return False
        
        try:
            # 读取JSON文件（支持JSONL格式）
            logger.info(f"读取数据文件: {json_file}")
            data = []
            
            with open(json_file, 'r', encoding='utf-8') as f:
                # 尝试读取为标准JSON
                content = f.read().strip()
                
                # 检查是否是JSONL格式（每行一个JSON对象）
                if content.startswith('{') and '\n{' in content:
                    logger.info("检测到JSONL格式，按行解析...")
                    f.seek(0)
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if line:
                            try:
                                record = json.loads(line)
                                data.append(record)
                            except json.JSONDecodeError as e:
                                logger.warning(f"第 {line_num} 行JSON解析失败: {e}")
                                continue
                else:
                    # 尝试作为标准JSON数组解析
                    try:
                        data = json.loads(content)
                        if not isinstance(data, list):
                            logger.error("JSON文件格式错误，应该是数组格式或JSONL格式")
                            return False
                    except json.JSONDecodeError:
                        logger.error("文件既不是标准JSON数组也不是JSONL格式")
                        return False
            
            logger.info(f"共读取 {len(data)} 条记录")
            
            # 转换数据
            logger.info("开始转换数据...")
            transformed_data = []
            
            for i, record in enumerate(data):
                try:
                    transformed = self.transform_record(record)
                    
                    # 保留原有的ID
                    doc_id = record.get('_id')
                    if not doc_id:
                        logger.warning(f"记录 {i} 缺少 _id 字段，跳过")
                        continue
                    
                    transformed_data.append({
                        'id': doc_id,  # 使用原有ID
                        'data': transformed
                    })
                    
                    if (i + 1) % 1000 == 0:
                        logger.info(f"已转换 {i + 1} 条记录")
                        
                except Exception as e:
                    logger.warning(f"转换记录 {i} 失败: {e}")
                    continue
            
            logger.info(f"成功转换 {len(transformed_data)} 条记录")
            
            if not transformed_data:
                logger.error("没有有效的数据可以导入")
                return False
            
            # 批量导入
            logger.info("开始批量导入到 OpenSearch...")
            success_count = 0
            error_count = 0
            
            for i in range(0, len(transformed_data), batch_size):
                batch = transformed_data[i:i + batch_size]
                
                # 构建批量操作
                bulk_body = []
                for item in batch:
                    bulk_body.append({
                        "index": {
                            "_index": index_name,
                            "_id": item['id']  # 使用原有ID
                        }
                    })
                    bulk_body.append(item['data'])
                
                try:
                    response = self.client.bulk(body=bulk_body)
                    
                    # 检查结果
                    for item in response['items']:
                        if 'index' in item:
                            if item['index']['status'] in [200, 201]:
                                success_count += 1
                            else:
                                error_count += 1
                                logger.warning(f"导入失败: {item['index'].get('error', 'Unknown error')}")
                    
                    logger.info(f"已导入 {min(i + batch_size, len(transformed_data))}/{len(transformed_data)} 条记录")
                    
                except Exception as e:
                    logger.error(f"批量导入失败: {e}")
                    error_count += len(batch)
            
            logger.info(f"导入完成: 成功 {success_count} 条, 失败 {error_count} 条")
            
            # 刷新索引
            self.client.indices.refresh(index=index_name)
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"导入数据失败: {e}")
            return False

    def search_phenomena(self, query: str, system: str = None, part: str = None, size: int = 10):
        """按照 README.md 设计进行故障现象搜索"""
        try:
            # 构建搜索查询
            search_body = {
                "query": {
                    "bool": {
                        "must": {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "text^3",           # 故障现象文本权重最高
                                    "discussion^2",     # 故障点描述权重次之
                                    "search_content^1", # 完整内容权重最低
                                    "vehicletype^1.5"   # 车型信息
                                ],
                                "type": "best_fields",
                                "fuzziness": "AUTO"
                            }
                        },
                        "filter": []
                    }
                },
                "size": size,
                "highlight": {
                    "fields": {
                        "text": {"fragment_size": 150, "number_of_fragments": 1},
                        "discussion": {"fragment_size": 100, "number_of_fragments": 1}
                    }
                },
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"popularity": {"order": "desc"}}
                ]
            }
            
            # 添加系统过滤
            if system:
                search_body["query"]["bool"]["filter"].append({
                    "term": {"system.keyword": system}
                })
            
            # 添加部件过滤
            if part:
                search_body["query"]["bool"]["filter"].append({
                    "match": {"part": part}
                })
            
            response = self.client.search(index=INDEX_CONFIG['name'], body=search_body)
            
            results = []
            for hit in response['hits']['hits']:
                source = hit['_source']
                result = {
                    "id": hit['_id'],
                    "text": source.get('text', ''),
                    "system": source.get('system', ''),
                    "part": source.get('part', ''),
                    "tags": source.get('tags', []),
                    "vehicletype": source.get('vehicletype', ''),
                    "popularity": source.get('popularity', 0),
                    "score": hit['_score'],
                    "highlight": hit.get('highlight', {})
                }
                results.append(result)
            
            return {
                "query": query,
                "total": response['hits']['total']['value'],
                "results": results
            }
            
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return {"query": query, "total": 0, "results": []}

def main():
    """主函数"""
    print("🚀 导入 servicingcase_last.json 到 OpenSearch")
    print("保留所有原有字段，支持故障现象匹配")
    print("=" * 60)
    
    # 数据文件路径
    data_file = os.path.join(os.path.dirname(__file__), '../data/servicingcase_last.json')
    
    if not os.path.exists(data_file):
        logger.error(f"数据文件不存在: {data_file}")
        return False
    
    logger.info(f"数据文件: {data_file}")
    logger.info(f"目标索引: {INDEX_CONFIG['name']}")
    logger.info(f"OpenSearch: {OPENSEARCH_CONFIG['host']}:{OPENSEARCH_CONFIG['port']}")
    
    try:
        # 创建导入器
        importer = OpenSearchImporterPreserveFields()
        
        # 导入数据
        success = importer.import_data(
            json_file=data_file,
            index_name=INDEX_CONFIG['name'],
            batch_size=IMPORT_CONFIG['batch_size']
        )
        
        if success:
            print("\n🎉 数据导入成功!")
            
            # 进行故障现象搜索测试
            print("\n🔍 进行故障现象搜索测试...")
            test_queries = [
                {"query": "发动机无法启动", "system": "发动机"},
                {"query": "刹车发软", "system": "制动"},
                {"query": "变速器挂档冲击", "system": "变速箱/传动"},
                {"query": "空调不制冷", "system": "空调"}
            ]
            
            for test in test_queries:
                print(f"\n测试查询: {test['query']} (系统: {test.get('system', '全部')})")
                results = importer.search_phenomena(
                    query=test['query'],
                    system=test.get('system'),
                    size=3
                )
                
                print(f"找到 {results['total']} 个相关案例:")
                for i, result in enumerate(results['results'], 1):
                    print(f"  {i}. [{result['id']}] {result['text'][:100]}...")
                    print(f"     车型: {result['vehicletype']}, 系统: {result['system']}")
                    print(f"     评分: {result['score']:.2f}, 热度: {result['popularity']}")
            
            print(f"\n✅ 导入完成! 索引名称: {INDEX_CONFIG['name']}")
            print(f"💡 可以使用 /match API 进行故障现象匹配查询")
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

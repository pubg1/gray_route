#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 servicingcase_last.json 数据导入 OpenSearch
"""

import json
import os
import re
import importlib
from typing import Dict, List, Any, Optional, Tuple
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk
import argparse
import sys
from datetime import datetime
import logging

# 为了复用应用内的向量模型工具，确保可以导入 app 模块
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

embedding_spec = importlib.util.find_spec("app.embedding")
if embedding_spec is not None:
    embedding_module = importlib.import_module("app.embedding")
    get_embedder = getattr(embedding_module, "get_embedder", None)
else:  # pragma: no cover - 离线导入脚本允许缺省模型
    get_embedder = None

sentence_spec = importlib.util.find_spec("sentence_transformers")
if sentence_spec is not None:
    sentence_module = importlib.import_module("sentence_transformers")
    SentenceTransformer = getattr(sentence_module, "SentenceTransformer", None)
else:  # pragma: no cover - 仅用于命令行导入
    SentenceTransformer = None

huggingface_spec = importlib.util.find_spec("huggingface_hub")
if huggingface_spec is not None:
    huggingface_module = importlib.import_module("huggingface_hub")
    snapshot_download = getattr(huggingface_module, "snapshot_download", None)
else:  # pragma: no cover - huggingface_hub 为可选依赖
    snapshot_download = None


class _SentenceTransformerWrapper:
    def __init__(self, model):
        self.model = model

    def encode(self, texts: List[str]):
        return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

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
                 timeout: int = 30,
                 enable_vector: bool = False,
                 vector_field: str = 'text_vector',
                 vector_dimension: int = 512,
                 embedding_model: Optional[str] = None):
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

        self.enable_vector = bool(enable_vector)
        self.vector_field = vector_field if vector_field else None
        self.vector_dimension = vector_dimension
        self.embedding_model = embedding_model
        self.embedder = None

        if self.enable_vector and not self.vector_field:
            logger.warning("未指定向量字段名称，已禁用语义向量写入功能")
            self.enable_vector = False

        if self.enable_vector and self.vector_field:
            self.embedder = self._load_embedder()
            if self.embedder is not None:
                logger.info(
                    "已启用语义向量写入: 字段=%s, 维度=%s",
                    self.vector_field,
                    self.vector_dimension,
                )
            else:
                logger.warning("未能加载向量模型，已自动关闭语义向量写入功能")
                self.enable_vector = False
    
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

    def _load_embedder(self):
        """加载向量模型"""
        model_id = self._infer_model_id()
        if SentenceTransformer is not None:
            local_path = self._ensure_model_download(model_id)
            load_target = local_path or model_id
            try:
                model = SentenceTransformer(load_target, trust_remote_code=True)
                logger.info("已加载 embedding 模型: %s", model_id)
                embedder = _SentenceTransformerWrapper(model)
                self._sync_vector_dimension(embedder)
                return embedder
            except Exception as model_err:
                logger.error(f"加载 SentenceTransformer 模型失败: {model_err}")

        if get_embedder is not None:
            try:
                embedder = get_embedder()
                self._sync_vector_dimension(embedder)
                logger.info("已回退到应用内置 embedding 模型")
                return embedder
            except Exception as fallback_err:
                logger.error(f"加载应用内置 embedding 模型失败: {fallback_err}")

        logger.error("当前环境未能加载任何向量模型，无法写入 knn 向量")
        return None

    def _infer_model_id(self) -> str:
        if self.embedding_model:
            return self.embedding_model

        config_spec = importlib.util.find_spec("app.config")
        if config_spec is not None:
            try:
                config_module = importlib.import_module("app.config")
                get_settings = getattr(config_module, "get_settings", None)
                if callable(get_settings):
                    settings = get_settings()
                    candidate = getattr(settings, "embedding_model", None)
                    if candidate:
                        return str(candidate)
            except Exception as cfg_err:
                logger.debug("读取应用默认 embedding 模型失败: %s", cfg_err)

        return "BAAI/bge-small-zh-v1.5"

    def _ensure_model_download(self, model_id: str) -> Optional[str]:
        if snapshot_download is None:
            logger.debug("huggingface_hub 未安装，跳过模型预下载")
            return None

        try:
            download_kwargs = {"repo_id": model_id, "local_dir_use_symlinks": False}
            preferred_home = os.environ.get("SENTENCE_TRANSFORMERS_HOME") or os.environ.get("HF_HOME")
            if preferred_home:
                target_dir = os.path.join(preferred_home, os.path.basename(model_id))
                os.makedirs(target_dir, exist_ok=True)
                download_kwargs["local_dir"] = target_dir
            local_path = snapshot_download(**download_kwargs)
            logger.info("embedding 模型已准备就绪: %s", local_path)
            return local_path
        except Exception as download_err:
            logger.warning("预下载 embedding 模型失败: %s", download_err)
            return None

    def _sync_vector_dimension(self, embedder: Any) -> None:
        try:
            preview = embedder.encode(["test"])
        except Exception as encode_err:
            raise RuntimeError(f"校验 embedding 模型输出失败: {encode_err}") from encode_err

        if preview is None:
            raise RuntimeError("embedding 模型未返回向量结果")

        if hasattr(preview, "tolist"):
            preview_list = preview.tolist()
        else:
            preview_list = list(preview)

        if not preview_list:
            raise RuntimeError("embedding 模型返回空向量")

        first_vector = preview_list[0] if isinstance(preview_list[0], (list, tuple)) else preview_list
        actual_dim = len(first_vector)
        if actual_dim != self.vector_dimension:
            logger.warning(
                "模型输出维度(%s)与配置维度(%s)不一致，自动更新配置",
                actual_dim,
                self.vector_dimension,
            )
            self.vector_dimension = int(actual_dim)

    @staticmethod
    def _build_embedding_text(document: Dict[str, Any]) -> str:
        """为向量模型准备文本"""
        parts = [
            document.get('symptoms', ''),
            document.get('discussion', ''),
            document.get('solution', ''),
            document.get('search_content', ''),
        ]
        combined = '\n'.join(part for part in parts if part)
        return combined.strip()

    def _apply_vectors(self, documents: List[Dict[str, Any]], texts: List[Optional[str]]):
        if not self.enable_vector or not self.embedder or not self.vector_field:
            return

        candidates: List[Tuple[int, str]] = [
            (idx, text) for idx, text in enumerate(texts) if text
        ]
        if not candidates:
            logger.info("没有可用于生成向量的文本")
            return

        indices, corpora = zip(*candidates)
        try:
            vectors = self.embedder.encode(list(corpora))
        except Exception as e:
            logger.error(f"批量生成向量失败: {e}")
            return

        try:
            vectors_list = vectors.tolist()  # type: ignore[attr-defined]
        except AttributeError:
            vectors_list = [list(vec) for vec in vectors]

        applied = 0
        for doc_idx, vector in zip(indices, vectors_list):
            if len(vector) != self.vector_dimension:
                logger.warning(
                    "文档 %s 的向量维度 %s 与配置 %s 不一致，已跳过",
                    documents[doc_idx].get('_id'),
                    len(vector),
                    self.vector_dimension,
                )
                continue
            documents[doc_idx]['_source'][self.vector_field] = vector
            applied += 1

        logger.info("已为 %s 条文档写入语义向量", applied)
    
    def create_index_mapping(self, index_name: str):
        """创建索引映射 - 使用简化配置避免AWS限制"""
        try:
            if self.client.indices.exists(index=index_name):
                logger.info(f"索引 {index_name} 已存在")
                return True

            properties = {
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
                "source_type": {"type": "keyword"},
            }

            if self.enable_vector and self.vector_field:
                properties[self.vector_field] = {
                    "type": "knn_vector",
                    "dimension": self.vector_dimension,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib",
                        "parameters": {
                            "ef_construction": 128,
                            "m": 16
                        }
                    }
                }

            simple_mapping = {
                "mappings": {
                    "properties": properties
                }
            }

            if self.enable_vector and self.vector_field:
                simple_mapping["settings"] = {
                    "index.knn": True,
                    "index.knn.space_type": "cosinesimil"
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
            documents: List[Dict[str, Any]] = []
            embedding_texts: List[Optional[str]] = [] if self.enable_vector else []
            for record in data:
                try:
                    transformed = self.transform_record(record)
                    if transformed:
                        if self.enable_vector:
                            embedding_texts.append(self._build_embedding_text(transformed))
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

            if self.enable_vector and documents:
                logger.info("开始批量生成语义向量...")
                self._apply_vectors(documents, embedding_texts)
            
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
    parser.add_argument('--enable-vector', action='store_true', help='写入语义向量并创建kNN索引')
    parser.add_argument('--vector-field', default='text_vector', help='向量字段名称 (默认: text_vector)')
    parser.add_argument('--vector-dim', type=int, default=512, help='向量维度 (默认: 512)')
    parser.add_argument('--embedding-model', help='自定义 SentenceTransformer 模型名称')
    parser.add_argument('--test', action='store_true', help='导入后进行搜索测试')

    args = parser.parse_args()
    
    try:
        # 创建导入器
        importer = OpenSearchImporter(
            host=args.host,
            port=args.port,
            username=args.username,
            password=args.password,
            use_ssl=args.ssl,
            enable_vector=args.enable_vector,
            vector_field=args.vector_field,
            vector_dimension=args.vector_dim,
            embedding_model=args.embedding_model,
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

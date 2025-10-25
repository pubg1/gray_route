#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 servicingcase_last.json 数据导入 OpenSearch。

该脚本支持：
* 将原始 JSON 行数据转换成应用所需字段结构；
* 按批次写入 OpenSearch；
* 可选地启用 `knn_vector` 字段写入，并在需要时自动准备 embedding 模型。

脚本尽可能复用应用内部的 embedding 加载逻辑，同时在缺少依赖时优雅回退。
"""

from __future__ import annotations

import argparse
import copy
import importlib
import importlib.util
import json
import logging
import os
import re
import sys
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk

# 为了能够复用 app 内部的工具，将项目根目录加入 sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# 尝试加载应用内的 embedding 与配置模块（若缺失则在运行期回退）
embedding_spec = importlib.util.find_spec("app.embedding")
if embedding_spec is not None:
    embedding_module = importlib.import_module("app.embedding")
    get_embedder = getattr(embedding_module, "get_embedder", None)
else:  # pragma: no cover - 离线导入脚本允许缺省模型
    get_embedder = None

config_spec = importlib.util.find_spec("app.config")
if config_spec is not None:
    config_module = importlib.import_module("app.config")
    get_settings = getattr(config_module, "get_settings", None)
else:  # pragma: no cover - 命令行导入可脱离应用运行
    get_settings = None

sentence_spec = importlib.util.find_spec("sentence_transformers")
if sentence_spec is not None:
    sentence_module = importlib.import_module("sentence_transformers")
    SentenceTransformer = getattr(sentence_module, "SentenceTransformer", None)
else:  # pragma: no cover - sentence-transformers 为可选依赖
    SentenceTransformer = None

hf_spec = importlib.util.find_spec("huggingface_hub")
if hf_spec is not None:
    hf_module = importlib.import_module("huggingface_hub")
    snapshot_download = getattr(hf_module, "snapshot_download", None)
else:  # pragma: no cover - huggingface_hub 并非必需
    snapshot_download = None


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"


class _SentenceTransformerWrapper:
    """统一 SentenceTransformer 与应用内 Embedder 的接口。"""

    def __init__(self, model: Any):
        self.model = model

    def encode(self, texts: Sequence[str]):
        return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class OpenSearchImporter:
    @staticmethod
    def _coerce_bool(name: str, value: Any, *, default: bool = False) -> bool:
        """Normalize truthy configuration flags coming from shell/environment values."""

        if isinstance(value, bool):
            return value

        if value is None:
            return default

        if isinstance(value, (int, float)):
            if value in (0, 1):
                return bool(value)
            raise ValueError(
                f"OpenSearch {name} 配置无效: 仅支持 0/1 或布尔值"
            )

        if isinstance(value, str):
            normalized = value.strip().lower()
            if not normalized:
                return default
            if normalized in {"true", "1", "yes", "y", "on"}:
                return True
            if normalized in {"false", "0", "no", "n", "off"}:
                return False

        raise ValueError(f"OpenSearch {name} 配置无效: {value!r}")

    @classmethod
    def _normalize_ssl_assert_hostname(cls, value: Any, host: str) -> Any:
        """Sanitize the ``ssl_assert_hostname`` option for urllib3 compatibility."""

        if value is None:
            return host

        if isinstance(value, bool):
            return host if value else False

        if isinstance(value, (int, float)):
            if value in (0, 1):
                return host if bool(value) else False
            raise ValueError("OpenSearch ssl_assert_hostname 配置无效: 仅支持 0/1")

        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return host

            lowered = normalized.lower()
            if lowered in {"true", "1", "yes", "y", "on"}:
                return host
            if lowered in {"false", "0", "no", "n", "off"}:
                return False

            return normalized

        raise ValueError(f"OpenSearch ssl_assert_hostname 配置无效: {value!r}")

    @staticmethod
    def _normalize_host(raw_host: Any) -> str:
        """Ensure the OpenSearch host value is a non-empty hostname string."""

        if isinstance(raw_host, bool):
            raise ValueError(
                "OpenSearch host 配置不能是布尔值，请检查 OPENSEARCH_HOST 或配置文件"
            )

        if raw_host is None:
            return "localhost"

        host_str = str(raw_host).strip()
        if not host_str:
            raise ValueError(
                "OpenSearch host 配置为空，请在环境变量或 opensearch_config.py 中设置有效地址"
            )

        return host_str

    @staticmethod
    def _normalize_port(raw_port: Any) -> int:
        """Validate the OpenSearch port value and convert it to ``int``."""

        if isinstance(raw_port, bool) or raw_port is None:
            raise ValueError("OpenSearch port 配置无效，请提供正确的端口号")

        try:
            port_int = int(raw_port)
        except (TypeError, ValueError) as exc:
            raise ValueError("OpenSearch port 必须是整数") from exc

        if port_int <= 0:
            raise ValueError("OpenSearch port 必须是正整数")

        return port_int

    @classmethod
    def _normalize_endpoint(
        cls, raw_host: Any, raw_port: Any, use_ssl: Any
    ) -> Tuple[str, int, bool, Optional[str]]:
        """Parse host/port values and extract optional URL prefix information."""

        host_value = cls._normalize_host(raw_host)
        port_value = cls._normalize_port(raw_port)
        ssl_flag = cls._coerce_bool("use_ssl", use_ssl)

        # urlparse requires a scheme to reliably split host/port/path.
        default_scheme = "https" if ssl_flag else "http"
        parse_target = host_value if "://" in host_value else f"{default_scheme}://{host_value}"
        parsed = urlparse(parse_target)

        if not parsed.hostname:
            raise ValueError("OpenSearch host 配置无法解析出有效的主机名")

        host_value = parsed.hostname
        if parsed.port:
            port_value = parsed.port

        # Any explicit scheme in the host should override the passed-in flag.
        if parsed.scheme in {"http", "https"}:
            ssl_flag = parsed.scheme == "https"

        url_prefix = parsed.path.strip("/") if parsed.path and parsed.path != "/" else None

        return host_value, port_value, ssl_flag, url_prefix

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9200,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_ssl: bool = False,
        verify_certs: bool = False,
        ssl_assert_hostname: Any = True,
        ssl_show_warn: bool = True,
        timeout: int = 30,
        enable_vector: bool = False,
        vector_field: str = "text_vector",
        vector_dimension: int = 512,
        embedding_model: Optional[str] = None,
        model_cache_dir: Optional[str] = None,
        clone_source_index: Optional[str] = "automotive_cases",
        preserve_source_fields: bool = False,
        recreate_index: bool = False,
    ) -> None:
        """初始化 OpenSearch 连接并准备向量写入。"""

        try:
            use_ssl_flag = self._coerce_bool("use_ssl", use_ssl)
            verify_certs_flag = self._coerce_bool("verify_certs", verify_certs)
            ssl_assert_hostname_flag = self._coerce_bool(
                "ssl_assert_hostname", ssl_assert_hostname, default=True
            )
            ssl_show_warn_flag = self._coerce_bool(
                "ssl_show_warn", ssl_show_warn, default=True
            )
        except ValueError as exc:
            logger.error("无效的 OpenSearch 连接配置: %s", exc)
            raise

        try:
            host_value, port_value, use_ssl_flag, url_prefix = self._normalize_endpoint(
                host, port, use_ssl_flag
            )
        except ValueError as exc:
            logger.error("无效的 OpenSearch 连接配置: %s", exc)
            raise

        try:
            ssl_assert_hostname_value = self._normalize_ssl_assert_hostname(
                ssl_assert_hostname, host_value
            )
        except ValueError as exc:
            logger.error("无效的 OpenSearch 连接配置: %s", exc)
            raise

        if not verify_certs_flag:
            ssl_assert_hostname_value = None

        if isinstance(ssl_assert_hostname_value, bool):
            ssl_assert_hostname_value = host_value if ssl_assert_hostname_value else None

        self.config = {
            "hosts": [{"host": host_value, "port": port_value}],
            "http_compress": True,
            "use_ssl": use_ssl_flag,
            "verify_certs": verify_certs_flag,
            "ssl_assert_hostname": ssl_assert_hostname_flag,
            "ssl_show_warn": ssl_show_warn_flag,
            "timeout": timeout,
            "max_retries": 3,
            "retry_on_timeout": True,
        }

        if ssl_assert_hostname_value is not None:
            self.config["ssl_assert_hostname"] = ssl_assert_hostname_value

        if url_prefix:
            self.config["url_prefix"] = url_prefix

        if username and password:
            self.config["http_auth"] = (username, password)

        try:
            self.client = OpenSearch(**self.config)
            info = self.client.info()
            self.server_version = info.get("version", {}).get("number", "unknown")
            logger.info("成功连接到 OpenSearch: %s", self.server_version)
        except Exception as exc:  # pragma: no cover - 连接失败时直接抛出
            logger.error("连接 OpenSearch 失败: %s", exc)
            raise

        try:
            preserve_flag = self._coerce_bool(
                "preserve_source_fields", preserve_source_fields
            )
            recreate_flag = self._coerce_bool("recreate_index", recreate_index)
        except ValueError as exc:
            logger.error("无效的 OpenSearch 连接配置: %s", exc)
            raise

        self.enable_vector = bool(enable_vector)
        self.vector_field = vector_field.strip() if vector_field else ""
        self.vector_dimension = vector_dimension
        self.embedding_model = embedding_model.strip() if embedding_model else None
        self.model_cache_dir = model_cache_dir.strip() if model_cache_dir else None
        self.clone_source_index = (
            clone_source_index.strip() if clone_source_index else None
        )
        self.preserve_source_fields = preserve_flag
        self.recreate_index = recreate_flag
        self.embedder: Optional[Any] = None
        self._prepared_model_path: Optional[str] = None

        if self.model_cache_dir:
            self._configure_model_cache_env()

        if self.enable_vector:
            if not self.vector_field:
                logger.warning("未指定向量字段名称，已禁用语义向量写入功能")
                self.enable_vector = False
            else:
                self.embedding_model = self.embedding_model or self._infer_embedding_model()
                self.embedder = self._load_embedder()
                if self.embedder is None:
                    logger.warning("未能加载向量模型，已自动关闭语义向量写入功能")
                    self.enable_vector = False
                else:
                    self._sync_vector_dimension()
                    logger.info(
                        "已启用语义向量写入: 字段=%s, 维度=%s, 模型=%s",
                        self.vector_field,
                        self.vector_dimension,
                        self.embedding_model or "未知",
                    )

    # ------------------------------------------------------------------
    # 模型准备相关工具
    # ------------------------------------------------------------------
    def _configure_model_cache_env(self) -> None:
        os.makedirs(self.model_cache_dir, exist_ok=True)
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", self.model_cache_dir)
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", self.model_cache_dir)
        logger.info("模型缓存目录: %s", self.model_cache_dir)

    def _infer_embedding_model(self) -> str:
        if self.embedding_model:
            return self.embedding_model

        if get_settings:
            try:
                settings = get_settings()
                model_name = getattr(settings, "embedding_model", None)
                if model_name:
                    return model_name
            except Exception as exc:  # pragma: no cover - 设置加载失败时降级
                logger.debug("读取应用配置失败: %s", exc)

        return DEFAULT_EMBEDDING_MODEL

    def _prepare_model_snapshot(self, model_id: str) -> Optional[str]:
        if snapshot_download is None:
            return None

        kwargs: Dict[str, Any] = {}
        if self.model_cache_dir:
            kwargs["cache_dir"] = self.model_cache_dir
        token = os.getenv("HUGGINGFACEHUB_API_TOKEN") or os.getenv("HF_TOKEN")
        if token:
            kwargs["token"] = token

        try:
            local_dir = snapshot_download(
                repo_id=model_id,
                local_files_only=False,
                resume_download=True,
                **kwargs,
            )
            logger.info("已预下载模型 %s -> %s", model_id, local_dir)
            return local_dir
        except Exception as exc:
            logger.warning("预下载模型失败（使用在线加载）: %s", exc)
            return None

    def _wrap_embedder(self, embedder: Any) -> Any:
        if embedder is None:
            return None
        if hasattr(embedder, "encode"):
            return embedder
        return None

    def _load_embedder(self) -> Optional[Any]:
        # 优先复用 app.embedding 提供的缓存实例
        if get_embedder is not None and not self.embedding_model:
            try:
                embedder = get_embedder()
                logger.info("复用 app.embedding.get_embedder() 提供的模型实例")
                inferred = self._detect_model_name(embedder)
                if inferred:
                    self.embedding_model = inferred
                return self._wrap_embedder(embedder)
            except Exception as exc:
                logger.warning("加载应用内嵌入模型失败，将尝试直接加载: %s", exc)

        model_name = self.embedding_model or self._infer_embedding_model()
        if SentenceTransformer is None:
            logger.warning("未安装 sentence_transformers，无法写入语义向量")
            return None

        if self._prepared_model_path is None:
            self._prepared_model_path = self._prepare_model_snapshot(model_name)
        load_path = self._prepared_model_path or model_name

        try:
            model = SentenceTransformer(load_path, trust_remote_code=True)
            self.embedding_model = model_name
            return _SentenceTransformerWrapper(model)
        except Exception as exc:
            logger.error("加载模型 %s 失败: %s", model_name, exc)
            return None

    def _detect_model_name(self, embedder: Any) -> Optional[str]:
        candidate = getattr(embedder, "model", None)
        if candidate is None:
            return None
        for attr in ("name_or_path", "model_name", "model_id"):
            value = getattr(candidate, attr, None)
            if isinstance(value, str) and value:
                return value
        return None

    def _sync_vector_dimension(self) -> None:
        if self.embedder is None:
            return

        model = getattr(self.embedder, "model", None)
        dimension = None
        if model is not None:
            getter = getattr(model, "get_sentence_embedding_dimension", None)
            if callable(getter):
                try:
                    dimension = int(getter())
                except Exception:  # pragma: no cover - 极端情况下尝试回退
                    dimension = None

        if dimension is None:
            try:
                probe = self.embedder.encode(["dimension probe"])
                vector = self._normalize_vector_output(probe)
                if vector:
                    dimension = len(vector)
            except Exception:
                dimension = None

        if dimension and dimension != self.vector_dimension:
            logger.info(
                "自动调整向量维度: 配置=%s, 模型=%s",
                self.vector_dimension,
                dimension,
            )
            self.vector_dimension = dimension

    # ------------------------------------------------------------------
    # 文本清洗 & 文档构建
    # ------------------------------------------------------------------
    def clean_html_content(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def extract_symptoms_and_solution(self, search_content: str) -> Dict[str, str]:
        if not search_content:
            return {"symptoms": "", "solution": ""}

        clean_content = self.clean_html_content(search_content)
        sentences = [s for s in clean_content.split("。") if s]

        symptoms = ""
        if sentences:
            symptoms = "。".join(sentences[:3]).strip()
            if symptoms and not symptoms.endswith("。"):
                symptoms += "。"

        solution = ""
        solution_keywords = ["更换", "维修", "解决", "处理", "修复", "故障排除"]
        for sentence in sentences:
            if any(keyword in sentence for keyword in solution_keywords):
                solution = sentence.strip()
                break

        return {
            "symptoms": symptoms[:500] if symptoms else "",
            "solution": solution[:300] if solution else "",
        }

    def _should_replace_field(self, current: Any) -> bool:
        if current is None:
            return True
        if isinstance(current, str):
            return not current.strip()
        if isinstance(current, (list, tuple, set)):
            return len(current) == 0
        return False

    def transform_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        source = record.get("_source") or {}
        transformed: Dict[str, Any] = copy.deepcopy(source)

        doc_id = record.get("_id") or transformed.get("id")
        if not doc_id:
            logger.debug("记录缺少 id，已跳过: %s", record)
            return None

        if self.preserve_source_fields:
            if (
                "id" not in transformed
                or self._should_replace_field(transformed.get("id"))
            ):
                transformed["id"] = doc_id

            if (
                self.enable_vector
                and self.embedder is not None
                and self.vector_field
                and (
                    self.vector_field not in transformed
                    or self._should_replace_field(transformed.get(self.vector_field))
                )
            ):
                text_for_vector = (
                    transformed.get("search_content")
                    or transformed.get("search")
                    or transformed.get("discussion")
                    or transformed.get("symptoms")
                    or ""
                )
                vector = self._build_vector(text_for_vector)
                if vector is not None:
                    transformed[self.vector_field] = vector

            return transformed

        transformed.setdefault("id", doc_id)
        transformed.setdefault("source_index", record.get("_index"))
        transformed.setdefault("source_type", record.get("_type"))

        search_content = source.get("search", "")
        extracted = self.extract_symptoms_and_solution(search_content)

        if self._should_replace_field(transformed.get("symptoms")):
            symptoms = extracted.get("symptoms")
            if symptoms:
                transformed["symptoms"] = symptoms

        if self._should_replace_field(transformed.get("solution")):
            solution = extracted.get("solution")
            if solution:
                transformed["solution"] = solution

        cleaned_search = self.clean_html_content(search_content)[:2000]
        if cleaned_search and self._should_replace_field(transformed.get("search_content")):
            transformed["search_content"] = cleaned_search

        if self._should_replace_field(transformed.get("import_time")):
            transformed["import_time"] = datetime.now().isoformat()

        if (
            self._should_replace_field(transformed.get("search_num"))
            and "searchNum" in source
        ):
            transformed["search_num"] = source.get("searchNum")

        if self.enable_vector and self.embedder is not None:
            text_for_vector = (
                transformed.get("search_content")
                or transformed.get("discussion")
                or transformed.get("symptoms")
                or ""
            )
            vector = self._build_vector(text_for_vector)
            if vector is not None:
                transformed[self.vector_field] = vector

        return transformed

    def _normalize_vector_output(self, batch: Any) -> Optional[List[float]]:
        if batch is None:
            return None

        if hasattr(batch, "tolist"):
            batch = batch.tolist()
        if not isinstance(batch, Iterable):
            return None

        batch_list = list(batch)
        if not batch_list:
            return None

        first = batch_list[0]
        if isinstance(first, Iterable) and not isinstance(first, (str, bytes)):
            vector = list(first)
        else:
            vector = batch_list

        try:
            return [float(x) for x in vector]
        except (TypeError, ValueError):
            logger.warning("向量结果无法转换为 float: %s", vector)
            return None

    def _build_vector(self, text: str) -> Optional[List[float]]:
        content = text.strip()
        if not content:
            return None
        try:
            batch = self.embedder.encode([content])
        except Exception as exc:
            logger.warning("生成语义向量失败: %s", exc)
            return None

        vector = self._normalize_vector_output(batch)
        if vector is None:
            return None

        if self.vector_dimension and len(vector) != self.vector_dimension:
            logger.warning(
                "向量维度与配置不一致: got=%s expected=%s，将按模型输出更新配置",
                len(vector),
                self.vector_dimension,
            )
            self.vector_dimension = len(vector)

        return vector

    # ------------------------------------------------------------------
    # 索引管理 & 导入流程
    # ------------------------------------------------------------------
    def _fetch_source_mapping(self, source_index: str) -> Optional[Dict[str, Any]]:
        try:
            response = self.client.indices.get_mapping(index=source_index)
        except Exception as exc:
            logger.warning("无法读取源索引 %s 的映射: %s", source_index, exc)
            return None

        mapping = response.get(source_index, {}).get("mappings")
        if not mapping:
            return None

        return copy.deepcopy(mapping)

    def _build_default_mapping(self) -> Dict[str, Any]:
        return {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "vehicletype": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword"}},
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
            }
        }

    def create_index_mapping(self, index_name: str) -> bool:
        try:
            response = self.client.indices.get_mapping(index=source_index)
        except Exception as exc:
            logger.warning("无法读取源索引 %s 的映射: %s", source_index, exc)
            return None

        mapping = response.get(source_index, {}).get("mappings")
        if not mapping:
            return None

        return copy.deepcopy(mapping)

    def _build_default_mapping(self) -> Dict[str, Any]:
        return {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "vehicletype": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword"}},
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
            }
        }

    def create_index_mapping(self, index_name: str) -> bool:
        try:
            if self.client.indices.exists(index=index_name):
                if self.recreate_index:
                    try:
                        logger.info("索引 %s 已存在，将删除后重新创建", index_name)
                        self.client.indices.delete(index=index_name)
                    except Exception as exc:
                        logger.error("删除已存在索引失败: %s", exc)
                        return False
                else:
                    logger.info("索引 %s 已存在", index_name)
                    if self.enable_vector:
                        self._ensure_vector_compat(index_name)
                    return True

            body: Dict[str, Any]
            cloned = False

            if (
                self.clone_source_index
                and self.clone_source_index != index_name
            ):
                mapping = self._fetch_source_mapping(self.clone_source_index)
                if mapping:
                    body = {"mappings": mapping}
                    cloned = True
                    logger.info(
                        "已从索引 %s 克隆映射", self.clone_source_index
                    )
                else:
                    logger.warning(
                        "未能从索引 %s 克隆映射，将使用默认映射", self.clone_source_index
                    )

            if not cloned:
                body = self._build_default_mapping()

            if self.enable_vector:
                body.setdefault("settings", {})["index.knn"] = True
                properties = body.setdefault("mappings", {}).setdefault("properties", {})
                if self.vector_field in properties:
                    logger.info(
                        "向量字段 %s 已存在于映射中，将沿用现有定义", self.vector_field
                    )
                else:
                    properties[self.vector_field] = {
                        "type": "knn_vector",
                        "dimension": self.vector_dimension,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "nmslib",
                            "parameters": {
                                "ef_construction": 128,
                                "m": 16,
                            },
                        },
                    }

            self.client.indices.create(index=index_name, body=body)
            logger.info("成功创建索引: %s", index_name)
            return True
        except Exception as exc:
            logger.error("创建索引失败: %s", exc)
            logger.info("尝试跳过索引创建，直接导入数据…")
            return True

    def _ensure_vector_compat(self, index_name: str) -> None:
        try:
            mappings = self.client.indices.get_mapping(index=index_name)
            properties = mappings.get(index_name, {}).get("mappings", {}).get("properties", {})
        except Exception as exc:
            logger.warning("读取索引映射失败，无法校验向量字段: %s", exc)
            return

        vector_mapping = properties.get(self.vector_field)
        if not vector_mapping:
            try:
                body = {
                    "properties": {
                        self.vector_field: {
                            "type": "knn_vector",
                            "dimension": self.vector_dimension,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "nmslib",
                                "parameters": {
                                    "ef_construction": 128,
                                    "m": 16,
                                },
                            },
                        }
                    }
                }
                self.client.indices.put_mapping(index=index_name, body=body)
                logger.info("已在索引 %s 中添加缺失的向量字段 %s", index_name, self.vector_field)
            except Exception as exc:
                logger.warning(
                    "无法在索引 %s 中添加向量字段 %s，已禁用向量写入: %s",
                    index_name,
                    self.vector_field,
                    exc,
                )
                self.enable_vector = False
                return
        else:
            dimension = vector_mapping.get("dimension")
            if dimension and int(dimension) != self.vector_dimension:
                logger.info(
                    "索引已有向量字段，自动同步维度: %s -> %s",
                    self.vector_dimension,
                    dimension,
                )
                self.vector_dimension = int(dimension)

        try:
            settings = self.client.indices.get_settings(index=index_name)
            index_settings = settings.get(index_name, {}).get("settings", {}).get("index", {})
            knn_enabled = str(index_settings.get("knn", "false")).lower() in {"true", "1", "yes"}
            if not knn_enabled:
                logger.warning(
                    "索引 %s 未开启 index.knn，向量查询可能失败，请手动开启",
                    index_name,
                )
        except Exception:
            pass

    def import_data(self, json_file: str, index_name: str, batch_size: int = 100) -> bool:
        if not os.path.exists(json_file):
            logger.error("数据文件不存在: %s", json_file)
            return False

        if batch_size <= 0:
            batch_size = 100

        if not self.create_index_mapping(index_name):
            return False

        actions: List[Dict[str, Any]] = []
        total = 0

        for record in self._iter_records(json_file):
            transformed = self.transform_record(record)
            if not transformed:
                continue

            doc_id = transformed.get("id")
            action = {
                "_index": index_name,
                "_id": doc_id,
                "_source": transformed,
            }
            actions.append(action)

            if len(actions) >= batch_size:
                total += self._flush_bulk(actions)
                actions = []

        if actions:
            total += self._flush_bulk(actions)

        logger.info("成功导入 %s 条文档", total)
        return True

    def _iter_records(self, json_file: str) -> Iterable[Dict[str, Any]]:
        with open(json_file, "r", encoding="utf-8") as handle:
            for line_num, line in enumerate(handle, 1):
                text = line.strip()
                if not text:
                    continue
                try:
                    yield json.loads(text)
                except json.JSONDecodeError as exc:
                    logger.warning("第 %s 行 JSON 解析失败: %s", line_num, exc)
                    continue

    def _flush_bulk(self, actions: List[Dict[str, Any]]) -> int:
        if not actions:
            return 0

        try:
            success, errors = bulk(self.client, actions)
            if errors:
                logger.warning("Bulk 导入存在错误: %s", errors)
            return success
        except Exception as exc:
            logger.error("批量导入失败: %s", exc)
            return 0

    def run_test_query(self, index_name: str, query_text: str = "发动机故障") -> None:
        try:
            body = {
                "size": 5,
                "query": {
                    "multi_match": {
                        "query": query_text,
                        "fields": [
                            "discussion^3",
                            "symptoms^2",
                            "solution",
                            "search_content",
                        ],
                    }
                },
            }

            response = self.client.search(index=index_name, body=body)
            hits = response.get("hits", {}).get("hits", [])
            logger.info("测试查询返回 %s 条结果", len(hits))
            for idx, hit in enumerate(hits, 1):
                source = hit.get("_source", {})
                logger.info(
                    "[%s] 讨论: %s | 现象: %s",
                    idx,
                    source.get("discussion", ""),
                    source.get("symptoms", ""),
                )
        except Exception as exc:
            logger.warning("测试查询失败: %s", exc)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将 JSONL 数据导入 OpenSearch")
    parser.add_argument("--file", "-f", required=True, help="JSON 行文件路径")
    parser.add_argument("--index", "-i", default="automotive_cases", help="目标索引名称")
    parser.add_argument("--host", default="localhost", help="OpenSearch 主机")
    parser.add_argument("--port", type=int, default=9200, help="OpenSearch 端口")
    parser.add_argument("--username", "-u", help="用户名")
    parser.add_argument("--password", "-p", help="密码")
    parser.add_argument("--ssl", action="store_true", help="使用 SSL 连接")
    parser.add_argument("--verify-certs", action="store_true", help="验证 SSL 证书")
    parser.add_argument("--batch-size", type=int, default=100, help="批量导入大小")
    parser.add_argument("--timeout", type=int, default=30, help="请求超时 (秒)")

    # 向量相关参数
    parser.add_argument("--enable-vector", action="store_true", help="启用 knn_vector 写入")
    parser.add_argument("--vector-field", default="text_vector", help="向量字段名称")
    parser.add_argument("--vector-dim", type=int, default=512, help="向量维度")
    parser.add_argument("--embedding-model", help="SentenceTransformer 模型 ID")
    parser.add_argument("--model-cache", help="embedding 模型缓存目录")
    parser.add_argument(
        "--clone-mapping-from",
        default="automotive_cases",
        help="从指定索引克隆映射，保留所有原字段",
    )
    parser.add_argument(
        "--preserve-source-fields",
        action="store_true",
        help="保持原始 _source 字段不做额外填充，仅追加向量字段",
    )
    parser.add_argument(
        "--recreate-index",
        action="store_true",
        help="若索引已存在则删除后重新创建",
    )

    parser.add_argument("--test", action="store_true", help="导入完成后执行一次示例查询")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    try:
        importer = OpenSearchImporter(
            host=args.host,
            port=args.port,
            username=args.username,
            password=args.password,
            use_ssl=args.ssl,
            verify_certs=args.verify_certs,
            timeout=args.timeout,
            enable_vector=args.enable_vector,
            vector_field=args.vector_field,
            vector_dimension=args.vector_dim,
            embedding_model=args.embedding_model,
            model_cache_dir=args.model_cache,
            clone_source_index=args.clone_mapping_from,
            preserve_source_fields=args.preserve_source_fields,
            recreate_index=args.recreate_index,
        )
    except ValueError:
        return 1

    success = importer.import_data(args.file, args.index, batch_size=args.batch_size)

    if success and args.test:
        importer.run_test_query(args.index)

    return 0 if success else 1


if __name__ == "__main__":  # pragma: no cover - CLI 入口
    sys.exit(main())

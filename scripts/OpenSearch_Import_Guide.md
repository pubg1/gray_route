# OpenSearch 数据导入指南

## 概述

本指南将帮助你将 `servicingcase_last.json` 文件中的汽车维修案例数据导入到 OpenSearch 中，以便进行全文搜索和分析。

## 前置条件

### 1. OpenSearch 服务
确保 OpenSearch 服务正在运行：

```bash
# 使用 Docker 启动 OpenSearch (推荐)
docker run -d \
  --name opensearch \
  -p 9200:9200 \
  -p 9600:9600 \
  -e "discovery.type=single-node" \
  -e "OPENSEARCH_INITIAL_ADMIN_PASSWORD=MyStrongPassword123!" \
  opensearchproject/opensearch:latest

# 检查服务状态
curl http://localhost:9200
```

### 2. Python 依赖
安装必要的 Python 包：

```bash
# 自动安装依赖
python scripts/install_opensearch_deps.py

# 或手动安装
pip install opensearch-py requests urllib3
```

## 快速开始

### 1. 配置连接信息
编辑 `scripts/opensearch_config.py` 文件：

```python
OPENSEARCH_CONFIG = {
    'host': 'localhost',        # OpenSearch 主机地址
    'port': 9200,              # OpenSearch 端口
    'username': 'admin',       # 用户名（如果需要认证）
    'password': 'MyStrongPassword123!',  # 密码（如果需要认证）
    'use_ssl': False,          # 是否使用 SSL
    'verify_certs': False,     # 是否验证证书
}
```

### 2. 运行导入
```bash
# 进入脚本目录
cd scripts

# 运行简化导入脚本
python run_import.py

# 或使用完整功能脚本
python import_to_opensearch.py -f ../data/servicingcase_last.json -i automotive_cases
```

## 详细使用

### 数据结构转换

原始数据结构：
```json
{
  "_index": "servicingcase_last",
  "_type": "carBag", 
  "_id": "bc7ff60d313f4175a1912bbc4fd7e508",
  "_source": {
    "vehicletype": "CT4",
    "discussion": "变速器油型号错误",
    "search": "<div>详细的维修过程...</div>",
    "searchNum": 0
  }
}
```

转换后的结构：
```json
{
  "id": "bc7ff60d313f4175a1912bbc4fd7e508",
  "vehicletype": "CT4",
  "discussion": "变速器油型号错误",
  "symptoms": "该车变速器挂D档延迟并伴随冲击...",
  "solution": "更换变速器油后故障排除...",
  "search_content": "清理HTML后的完整内容",
  "search_num": 0,
  "created_at": "2025-10-14T19:27:00"
}
```

### 索引映射

创建的索引包含以下字段：

| 字段名 | 类型 | 描述 |
|--------|------|------|
| `id` | keyword | 唯一标识符 |
| `vehicletype` | text | 车型信息 |
| `discussion` | text | 故障点描述 |
| `symptoms` | text | 故障现象 |
| `solution` | text | 解决方案 |
| `search_content` | text | 完整搜索内容 |
| `search_num` | integer | 搜索次数 |
| `created_at` | date | 创建时间 |
| `text_vector`* | knn_vector | 语义检索向量 (可选) |

> \* 仅在执行脚本时添加 `--enable-vector` 时创建，该字段使用 `knn_vector` 类型并开启 `index.knn`。

### 命令行参数

完整脚本支持以下参数：

```bash
python import_to_opensearch.py [选项]

选项:
  -f, --file FILE       JSON文件路径 (必需)
  -i, --index INDEX    索引名称 (默认: automotive_cases)
  --host HOST          OpenSearch主机 (默认: localhost)
  --port PORT          OpenSearch端口 (默认: 9200)
  -u, --username USER  用户名
  -p, --password PASS  密码
  --ssl                使用SSL连接
  --batch-size SIZE    批量导入大小 (默认: 100)
  --enable-vector      写入语义向量并启用kNN索引配置
  --vector-field NAME  向量字段名称 (默认: text_vector)
  --vector-dim DIM     向量维度 (默认: 512)
  --embedding-model ID 自定义SentenceTransformer模型 (默认复用app.embedding配置)
  --test               导入后进行搜索测试
```

### 使用示例

```bash
# 基础导入
python import_to_opensearch.py -f ../data/servicingcase_last.json

# 指定索引名称
python import_to_opensearch.py -f ../data/servicingcase_last.json -i car_cases_2024

# 使用认证
python import_to_opensearch.py \
  -f ../data/servicingcase_last.json \
  -u admin -p MyPassword123! \
  --ssl

# 大批量导入
python import_to_opensearch.py \
  -f ../data/servicingcase_last.json \
  --batch-size 500 \
  --test

# 启用语义向量写入，构建kNN索引
python import_to_opensearch.py \
  -f ../data/servicingcase_last.json \
  --enable-vector \
  --vector-field text_vector \
  --vector-dim 512
```

### 选择和下载向量模型

脚本在启用 `--enable-vector` 时需要一个 SentenceTransformer 兼容的嵌入模型。默认情况下会复用应用配置中的 `EMBEDDING_MODEL`（位于 `app/config.py`，默认值为 `BAAI/bge-small-zh-v1.5`）。该模型针对中文语义检索进行了优化，发布在 [Hugging Face](https://huggingface.co/BAAI/bge-small-zh-v1.5) 上。

运行导入脚本时会自动尝试下载并缓存所需的模型：

* 如果环境已安装 `huggingface_hub`，脚本会在导入前调用 `snapshot_download` 预拉取模型文件。可通过设置 `SENTENCE_TRANSFORMERS_HOME` 或 `HF_HOME` 环境变量自定义缓存目录。
* 若未安装 `huggingface_hub`，则由 `SentenceTransformer` 在首次加载时自动下载到默认缓存目录（通常是 `~/.cache/huggingface`）。

> **提示**：如果你的环境无法联网，可提前在有网络的机器上下载模型，然后拷贝到离线环境的 `~/.cache/huggingface` 或者自定义的 `SENTENCE_TRANSFORMERS_HOME` 目录。

常见的下载方式：

```bash
# 使用 huggingface-cli 手动拉取（适合离线分发）
huggingface-cli download BAAI/bge-small-zh-v1.5 --local-dir /path/to/models/bge-small-zh-v1.5

# 或者在 Python 中预先加载，触发自动缓存
python - <<'PY'
from sentence_transformers import SentenceTransformer
SentenceTransformer('BAAI/bge-small-zh-v1.5', trust_remote_code=True)
PY
```

若需要使用其他模型，可将模型 ID 传入脚本：

```bash
python import_to_opensearch.py \
  -f ../data/servicingcase_last.json \
  --enable-vector \
  --embedding-model BAAI/bge-base-zh-v1.5
```

你也可以设置环境变量覆盖默认值：

```bash
export EMBEDDING_MODEL="moka-ai/m3e-base"
python import_to_opensearch.py -f ../data/servicingcase_last.json --enable-vector
```

选择模型时请确保输出向量维度与 `--vector-dim` 参数一致（常见中文模型如 `bge-small-zh` 为 512 维，`bge-base-zh` 为 768 维）。

## 搜索测试

导入完成后，可以进行搜索测试：

### 1. 基础搜索
```bash
curl -X GET "localhost:9200/automotive_cases/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "match": {
        "symptoms": "发动机"
      }
    }
  }'
```

### 2. 多字段搜索
```bash
curl -X GET "localhost:9200/automotive_cases/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "multi_match": {
        "query": "刹车发软",
        "fields": ["symptoms^2", "discussion^1.5", "solution"]
      }
    }
  }'
```

### 3. 车型过滤搜索
```bash
curl -X GET "localhost:9200/automotive_cases/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "bool": {
        "must": {
          "match": {"symptoms": "启动困难"}
        },
        "filter": {
          "term": {"vehicletype.keyword": "宋"}
        }
      }
    }
  }'
```

## 故障排查

### 常见问题

#### 1. 连接失败
```
❌ 连接 OpenSearch 失败: ConnectionError
```

**解决方法:**
- 检查 OpenSearch 服务是否运行: `curl http://localhost:9200`
- 检查防火墙设置
- 确认主机和端口配置正确

#### 2. 认证失败
```
❌ 连接 OpenSearch 失败: AuthenticationException
```

**解决方法:**
- 检查用户名和密码是否正确
- 确认是否需要SSL连接
- 检查用户权限

#### 3. 索引创建失败
```
❌ 创建索引失败: resource_already_exists_exception
```

**解决方法:**
- 删除现有索引: `curl -X DELETE "localhost:9200/automotive_cases"`
- 或使用不同的索引名称

#### 4. 导入数据为空
```
✅ 成功转换 0 条记录
```

**解决方法:**
- 检查JSON文件格式是否正确
- 确认文件路径是否存在
- 检查文件编码（应为UTF-8）

### 调试技巧

#### 1. 查看索引状态
```bash
# 查看所有索引
curl http://localhost:9200/_cat/indices?v

# 查看索引映射
curl http://localhost:9200/automotive_cases/_mapping

# 查看文档数量
curl http://localhost:9200/automotive_cases/_count
```

#### 2. 查看导入日志
脚本会输出详细的导入日志，包括：
- 连接状态
- 数据转换进度
- 批量导入结果
- 错误信息

#### 3. 手动测试单条记录
```python
# 测试脚本
from opensearchpy import OpenSearch

client = OpenSearch([{'host': 'localhost', 'port': 9200}])

# 插入测试文档
doc = {
    'vehicletype': '测试车型',
    'symptoms': '测试故障现象',
    'discussion': '测试故障点'
}

response = client.index(
    index='test_index',
    id='test_doc',
    body=doc
)
print(response)
```

## 性能优化

### 1. 批量大小调整
- 小文件: `--batch-size 50`
- 大文件: `--batch-size 500`
- 内存充足: `--batch-size 1000`

### 2. 索引设置优化
```python
# 在 import_to_opensearch.py 中调整
"settings": {
    "number_of_shards": 1,      # 单节点使用1个分片
    "number_of_replicas": 0,    # 开发环境不需要副本
    "refresh_interval": "30s"   # 降低刷新频率
}
```

### 3. 硬件要求
- **内存**: 最少 2GB，推荐 4GB+
- **磁盘**: 数据大小的 2-3 倍空间
- **CPU**: 2核心以上

## 集成到应用

导入完成后，可以在应用中使用 OpenSearch 进行搜索：

```python
from opensearchpy import OpenSearch

# 连接 OpenSearch
client = OpenSearch([{'host': 'localhost', 'port': 9200}])

# 搜索函数
def search_cases(query, vehicle_type=None, size=10):
    search_body = {
        "query": {
            "bool": {
                "must": {
                    "multi_match": {
                        "query": query,
                        "fields": ["symptoms^2", "discussion^1.5", "solution"]
                    }
                }
            }
        },
        "size": size
    }
    
    # 添加车型过滤
    if vehicle_type:
        search_body["query"]["bool"]["filter"] = {
            "term": {"vehicletype.keyword": vehicle_type}
        }
    
    response = client.search(index="automotive_cases", body=search_body)
    return response['hits']['hits']

# 使用示例
results = search_cases("发动机无法启动", vehicle_type="宋")
for hit in results:
    print(f"车型: {hit['_source']['vehicletype']}")
    print(f"故障: {hit['_source']['discussion']}")
    print(f"评分: {hit['_score']}")
```

## 维护和监控

### 1. 定期备份
```bash
# 创建快照仓库
curl -X PUT "localhost:9200/_snapshot/backup_repo" \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "fs",
    "settings": {
      "location": "/backup"
    }
  }'

# 创建快照
curl -X PUT "localhost:9200/_snapshot/backup_repo/snapshot_1"
```

### 2. 监控索引健康
```bash
# 查看集群健康状态
curl http://localhost:9200/_cluster/health

# 查看索引统计
curl http://localhost:9200/automotive_cases/_stats
```

### 3. 清理和重建
```bash
# 删除索引
curl -X DELETE "localhost:9200/automotive_cases"

# 重新导入
python run_import.py
```

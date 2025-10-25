# OpenSearch 数据导入指南

本文档说明如何把 `servicingcase_last.json` 数据集导入到 OpenSearch，并在需要时启用 `knn_vector` 字段以支持语义检索。

## 1. 环境准备

### 1.1 OpenSearch 服务
确保 OpenSearch 以及 Dashboards（可选）已经启动。最简单的方式是使用官方 Docker 镜像：

```bash
docker run -d \
  --name opensearch \
  -p 9200:9200 \
  -p 9600:9600 \
  -e "discovery.type=single-node" \
  -e "OPENSEARCH_INITIAL_ADMIN_PASSWORD=MyStrongPassword123!" \
  opensearchproject/opensearch:latest
```

> **提示**：如果运行在云端托管环境，请确认安全组/网络策略允许访问 9200 端口，并准备好账号密码。

### 1.2 Python 依赖
项目自带的导入脚本仅依赖 `opensearch-py`。若要写入语义向量，需要额外安装 `sentence-transformers` 与（可选）`huggingface_hub`：

```bash
# 安装基础依赖
pip install opensearch-py

# 如果要写入 knn_vector，请确保安装 embedding 相关依赖
pip install sentence-transformers huggingface-hub
```

若你的环境无法联网，可提前在有网络的机器上下载模型，然后通过 `--model-cache` 选项指定缓存目录。

## 2. 准备数据

默认数据文件位于 `data/servicingcase_last.json`，采用 JSONL（每行一个 JSON 对象）格式。如果文件在其他位置，可以通过脚本参数或环境变量覆盖。

## 3. 导入脚本 `import_to_opensearch.py`

该脚本支持以下功能：

- 自动清洗 HTML 内容并拆分出 `symptoms` / `solution` 字段；
- 批量写入 OpenSearch（默认 100 条一批，可通过 `--batch-size` 调整）；
- 可选地创建带 `knn_vector` 字段的索引并写入语义向量；
- 在具备 Hugging Face 访问权限时自动下载 embedding 模型，并支持 `--model-cache` 指定缓存目录；
- `--test` 选项可在导入完成后执行一次示例查询，快速验证数据是否可检索。

### 3.1 常用参数

```bash
python scripts/import_to_opensearch.py \
  --file data/servicingcase_last.json \
  --index automotive_cases \
  --host localhost \
  --port 9200 \
  --batch-size 200 \
  --test

# 启用语义向量写入，构建kNN索引
python import_to_opensearch.py \
  -f ../data/servicingcase_last.json \
  --enable-vector \
  --vector-field text_vector \
  --vector-dim 512
```

### 选择和下载向量模型

脚本在启用 `--enable-vector` 时需要一个 SentenceTransformer 兼容的嵌入模型。默认情况下会复用应用配置中的 `EMBEDDING_MODEL`（位于 `app/config.py`，默认值为 `BAAI/bge-small-zh-v1.5`）。该模型针对中文语义检索进行了优化，发布在 [Hugging Face](https://huggingface.co/BAAI/bge-small-zh-v1.5) 上，首次使用时会自动下载到本地缓存。

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

连接相关的可选参数包括 `--username/--password`、`--ssl` 和 `--verify-certs`。

### 3.2 启用 kNN 语义向量

要写入 `knn_vector` 字段并自动创建 kNN 索引，需要加上 `--enable-vector` 以及可选的模型参数：

```bash
python scripts/import_to_opensearch.py \
  --file data/servicingcase_last.json \
  --index cases \
  --enable-vector \
  --vector-field text_vector \
  --vector-dim 512 \
  --embedding-model BAAI/bge-small-zh-v1.5 \
  --model-cache /opt/opensearch-models
```

脚本会按以下顺序尝试加载 embedding：

1. 复用应用内的 `app.embedding.get_embedder()`；
2. 使用 `--embedding-model` 指定的 SentenceTransformer 模型；
3. 若未指定模型，则读取应用配置中的 `embedding_model`（默认 `BAAI/bge-small-zh-v1.5`）。

只要安装了 `huggingface_hub`，脚本会在运行前自动尝试使用 `snapshot_download` 将模型缓存到 `--model-cache` 指定目录；若未指定缓存目录，则使用 Hugging Face 默认缓存位置。缓存目录会通过 `SENTENCE_TRANSFORMERS_HOME` 与 `HUGGINGFACE_HUB_CACHE` 环境变量传递给下游库。

## 4. Shell 封装脚本 `import_cases_knn.sh`

为了方便快速导入 `cases` 索引，仓库提供了 `scripts/import_cases_knn.sh`：

```bash
./scripts/import_cases_knn.sh path/to/servicingcase_last.json
```

如果未传入参数，脚本会优先使用环境变量 `OPENSEARCH_DATA_FILE`，否则回退到 `data/servicingcase_last.json`。

常用环境变量说明：

| 变量 | 说明 | 默认值 |
| ---- | ---- | ------ |
| `OPENSEARCH_HOST` | OpenSearch 主机名 | `localhost` |
| `OPENSEARCH_PORT` | OpenSearch 端口 | `9200` |
| `OPENSEARCH_USERNAME` / `OPENSEARCH_PASSWORD` | 认证信息 | 空 |
| `OPENSEARCH_SSL` | 是否开启 `--ssl` | `false` |
| `OPENSEARCH_VERIFY_CERTS` | 是否传递 `--verify-certs` | `false` |
| `OPENSEARCH_TIMEOUT` | 请求超时时间（秒） | `30` |
| `OPENSEARCH_INDEX` | 索引名称 | `cases` |
| `OPENSEARCH_BATCH_SIZE` | 批量大小 | `200` |
| `OPENSEARCH_VECTOR_FIELD` | 向量字段 | `text_vector` |
| `OPENSEARCH_VECTOR_DIM` | 向量维度 | `512` |
| `EMBEDDING_MODEL` | 覆盖默认 embedding 模型 | 空（复用应用配置） |
| `MODEL_CACHE_DIR` | 模型缓存目录 | 空 |
| `PYTHON_BIN` | 指定 Python 解释器 | `python3` |

该脚本内部调用 `import_to_opensearch.py --enable-vector`，并自动传递上述参数。

## 5. 验证 kNN 功能

1. 导入完成后，执行 `GET /cases/_mapping`，确认映射中存在 `text_vector` 字段，类型为 `knn_vector`，且索引设置包含 `"index.knn": true`。
2. 调用 `GET /_plugins/_knn/stats`，观察 `knn_query_requests` 是否随查询增加。
3. 在应用或脚本中执行示例查询，验证语义检索结果。

若集群版本低于 2.9，顶层 `knn` 查询不可用，可在查询 DSL 中通过 `query.bool.must[].knn` 的形式嵌入语义检索；脚本生成的索引与向量字段同样可用。

## 6. 故障排查

- **提示 `Unknown key for a START_OBJECT in [knn]`**：索引未开启 `index.knn` 或集群版本过低。请升级到 OpenSearch ≥ 2.9，或在查询 DSL 中使用 `query.bool.must[].knn` 形式。
- **模型下载缓慢**：可提前使用 `huggingface-cli download` 或 `snapshot_download` 将模型缓存到本地，然后通过 `--model-cache` 指向缓存目录。
- **导入报错缺少 `sentence_transformers`**：安装 `sentence-transformers` 即可；如果只需关键字检索，可去掉 `--enable-vector`。

按照以上步骤操作，即可顺利将汽车案例数据导入 OpenSearch，并启用语义检索能力。

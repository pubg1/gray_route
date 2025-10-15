# 灰区路由语义匹配服务（macOS 本地部署 · 无 Docker）

本项目提供“方案 C｜灰区路由”的**纯本地实现**：
- 语义召回：**hnswlib**（HNSW 索引，替代 FAISS，macOS 免编译）
- 关键词召回：**TF-IDF（scikit-learn）**
- 精排：**Cross-Encoder**（transformers + torch，自动使用 CPU 或 Apple **MPS**）
- 灰区路由：仅在 0.65–0.84 区间调用 **LLM 闭集判别**（OpenAI 协议兼容）
- 后端：**FastAPI**（`/match`）

> 适合 macOS (Intel/Apple Silicon) 无 Docker、无 OpenSearch 的单机部署。

---

## 0. 依赖说明（macOS）

- macOS 13+（Intel 或 Apple Silicon）
- Python 3.10/3.11（建议）
- 推荐安装：`brew install git`（如需）

> **Torch/MPS**：Apple 芯片将自动使用 `mps`（Metal）加速精排；Intel 使用 CPU。

---

## 1. 一键部署（macOS）

```bash
cd codex-gray-route-macos

# 1) 初始化虚拟环境并安装依赖
bash scripts/bootstrap_macos.sh

# 2) 构建或加载检索索引（第一次会自动构建）
# （可选）手动预构建：
bash scripts/index_build_local.sh

# 3) 启动服务
bash scripts/run_local.sh

# 4) 打开 Swagger 文档：
# http://127.0.0.1:8080/docs
```

---

## 2. 快速调用

```bash
curl -G "http://127.0.0.1:8080/match" \
  --data-urlencode 'q=刹车发软 车身发飘' \
  --data-urlencode 'system=制动' \
  --data-urlencode 'part=制动踏板'
```

返回示例：
```json
{
  "query": "刹车发软 车身发飘",
  "top": [
    {"id":"P001","text":"制动踏板变软，制动距离变长","system":"制动","part":"制动踏板","tags":["刹车","变软"],"popularity":120,"bm25_score":0.0,"cosine":0.91,"rerank_score":8.12,"final_score":0.90,"why":["语义近","系统一致"]},
    {"id":"P003","text":"高速制动方向跑偏", ...}
  ],
  "decision": {"mode":"direct","chosen_id":"P001","confidence":0.90}
}
```

---

## 3. 环境变量（.env）

复制并编辑：
```bash
cp .env.example .env
```

- `OPENAI_API_BASE`、`OPENAI_API_KEY`、`OPENAI_MODEL`：用于灰区 LLM 闭集判别（可留空禁用）。
- `PASS_THRESHOLD`、`GRAY_LOW_THRESHOLD`：默认 `0.84 / 0.65`。
- `EMBEDDING_MODEL`：默认 `BAAI/bge-small-zh-v1.5`。
- `RERANKER_MODEL`：默认 `BAAI/bge-reranker-base`。
- `DATA_FILE`：现象库 JSONL 路径（默认 `data/phenomena_sample.jsonl`）。
- `HNSW_INDEX_PATH`：HNSW 索引路径（默认 `data/hnsw_index.bin`）。
- `TFIDF_CACHE_PATH`：TF-IDF 缓存路径（默认 `data/tfidf.pkl`）。

---

## 4. 目录结构

- `app/main.py`：FastAPI 接口（召回→精排→融合→灰区路由→兜底）
- `app/config.py`：配置/阈值/模型名
- `app/embedding.py`：嵌入编码器（Sentence-Transformers）
- `app/reranker.py`：Cross-Encoder 精排（自动选择 CPU/MPS）
- `app/searchers/hnswlib_index.py`：HNSW 召回（持久化）
- `app/searchers/keyword_tfidf.py`：TF-IDF 关键词召回（持久化缓存）
- `app/utils/normalize.py`：文本归一化、缩写、常错字
- `scripts/bootstrap_macos.sh`：创建 venv + 安装依赖
- `scripts/index_build_local.sh`：一键构建/更新 HNSW + TF-IDF
- `scripts/run_local.sh`：本地启动 FastAPI（Uvicorn）
- `data/phenomena_sample.jsonl`：样例数据

---

## 5. 自定义数据

将你的故障现象库整理为 **JSONL**（一行一个对象）：
```jsonl
{"id":"P001","text":"制动踏板变软，制动距离变长","system":"制动","part":"制动踏板","tags":["刹车","变软"],"popularity":120}
{"id":"P002","text":"ABS 警告灯常亮","system":"制动","part":"ABS系统","tags":["报警灯","ABS"],"popularity":180}
...
```
然后修改 `.env` 中的 `DATA_FILE` 并执行：
```bash
bash scripts/index_build_local.sh
```

---

## 6. 阈值/融合策略（默认）

- 路由阈值：`pass=0.84`，`gray_low=0.65`
- 候选规模：语义 Top-50 + 关键词 Top-50 → 精排 Top-10 → 返回 Top-3
- 融合：`0.55*rerank + 0.20*cosine + 0.10*bm25 + 0.10*kg_prior + 0.05*pop`

---

## 7. API 端点（默认开启）

- `GET /health`：返回当前可用的数据源（本地 HNSW/TF-IDF、OpenSearch、本地语义索引等）。
- `GET /match`：默认本地检索 + 精排 + 灰区路由闭集判别。
- `GET /match/hybrid`：在本地结果基础上，叠加 OpenSearch（如启用），并给出推荐策略。
- `POST /opensearch/match`：对接 OpenSearch 索引的召回/灰区路由（无本地索引也可用）。
- `GET /opensearch/stats`：查看当前 OpenSearch 索引文档统计（如启用）。

示例命令见 `docs/API_Documentation.md` 与 `OpenSearch_Integration_README.md`。

---

## 8. OpenSearch 集成（可选）

- 若需从远端 OpenSearch 检索，可使用 `scripts/deploy_complete_system.py`、`scripts/run_opensearch_import.py` 等脚本。
- 详细步骤、字段映射、混合匹配说明请参考 `OpenSearch_Integration_README.md`。
- `.env` 中的 `PASS_THRESHOLD`、`GRAY_LOW_THRESHOLD` 与 OpenSearch 召回保持一致，方便闭环调优。

---

## 9. 服务管理脚本

脚本目录位于 `scripts/`，常用操作如下：

- `bash scripts/run_local.sh`：后台启动服务，自动写入日志/ PID 文件。
- `bash scripts/status_local.sh`：查看运行状态、端口、健康检查。
- `bash scripts/restart_local.sh`：优雅重启；`bash scripts/stop_local.sh`：停止服务。
- 更多说明可见 `scripts/README.md`。

---

## 10. 许可证

MIT

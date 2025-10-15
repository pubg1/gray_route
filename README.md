# 灰区路由 OpenSearch + LLM 集成方案

本仓库提供一套面向汽车故障知识库的“灰区路由”实现，核心思路是：

1. **OpenSearch 高速召回** —— 保留业务字段并扩展 `text/system/part/tags` 等规范字段，通过 `multi_match` + 过滤器完成毫秒级候选检索；如需更高覆盖率，可叠加语义向量召回。
2. **规则判分与阈值决策** —— 根据相似度、系统/部件命中情况得到置信度分布，利用 `pass / gray_low` 双阈值直接返回高置信度结果或进入灰区。
3. **LLM 闭集甄选** —— 仅对灰区请求触发模型，通过 `closed_set_pick` 等提示在给定候选中选出答案或返回 `UNKNOWN`，最大化利用 LLM 能力同时控制时延。

> ✅ 目标：用 OpenSearch 处理绝大部分请求，把 LLM 放在“灰度兜底”环节，实现稳定的查询性能与更可靠的语义匹配效果。

---

## 1. 架构与流程

```
┌────────┐   ┌──────────────┐   ┌───────────────┐   ┌────────────┐
│  请求  │ → │ OpenSearch 召回 │ → │ 灰区决策 (规则) │ → │ 直接返回 │
└────────┘   └──────────────┘   └───────────────┘   └────────────┘
                                            │
                                            ▼
                                    ┌────────────┐
                                    │ LLM 闭集判别 │
                                    └────────────┘
                                            │
                                            ▼
                                       ┌────────┐
                                       │ 结果输出 │
                                       └────────┘
```

- **字段准备**：在导入 OpenSearch 时，除了保留原始 `_source`，还同步写入 `text`（标准化描述）、`system`、`part`、`tags`、`popularity` 等字段，便于多维检索与加权。
- **召回策略**：默认使用 `multi_match` + 过滤器（系统、部件、车型等），可按需开启 `dense_vector` 语义检索，以补充长尾场景。
- **灰区阈值**：建议初始设置 `pass=0.84`、`gray_low=0.65`，结合业务统计可微调；阈值越清晰，落入灰区（触发 LLM）的比例越低。
- **LLM 判别**：提示词限定为“封闭集合选择”，响应格式统一为 JSON，方便前后端解析，并可根据置信度回填前端。

---

## 2. 保证查询速度的关键实践

- **召回优先**：让 OpenSearch 完成 99% 的请求，只有低置信度时才调用 LLM，避免模型成为瓶颈。
- **候选裁剪**：`size`、`vector_k` 控制在几十条以内，传给 LLM 的字段压缩为 `id/text/system/part` 等最小集合，减少提示词长度。
- **提示精简**：要求模型只输出候选 ID + 简要理由，显著降低推理时长与 token 成本。
- **异步与超时**：FastAPI 层使用 `httpx.AsyncClient`，统一设置 20s 超时与降级策略，上游可继续执行其他逻辑或回退。
- **权重调优**：通过调节 `multi_match` 字段权重、热门文档加权、语义向量比例，让置信度分布更稳定，减少灰区请求量。
- **缓存与复用**：对热门查询、模型输出设置短期缓存，可显著降低 LLM 调用频次。

---

## 3. 部署指南

### 3.1 OpenSearch 准备

1. 启动/连接 OpenSearch 集群（自建或托管）。
2. 参考 `docs/schema/` 中的映射定义（示例），确保支持 `text`、`keyword`、`dense_vector` 等字段。
3. 执行 `scripts/run_opensearch_import.py` 或 `scripts/import_to_opensearch_preserve_fields.py`，在导入过程中：
   - 原始字段 **100% 保留**，无破坏性修改；
   - 自动生成标准化字段（归一化文本、系统、部件、标签、热门度等）；
   - 根据需要生成语义向量并写入 `dense_vector`。

### 3.2 API 服务

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-macos.txt  # 亦可选择 Linux/Windows 对应依赖

# 启动 FastAPI 服务（默认 0.0.0.0:8080）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

核心端点：

- `GET /health` —— 返回当前可用的数据源（本地 HNSW、OpenSearch、语义索引等）。
- `GET /match` —— 默认流程：OpenSearch 召回 → 规则判分 → 灰区路由 →（必要时）LLM。
- `GET /match/hybrid` —— 在本地检索基础上叠加 OpenSearch，并给出推荐策略。
- `POST /opensearch/match` —— 纯 OpenSearch 版本，可选择启用灰区决策与 LLM 精选，支持 `q/system/part/vehicletype/size` 等参数。
- `GET /opensearch/stats` —— 查看当前索引文档统计。

更多示例见 `docs/API_Documentation.md` 与 `OpenSearch_Integration_README.md`。

---

## 4. LLM 接入要点

- **提示模板**：推荐 `closed_set_pick` 风格，明确约束“必须在候选中选择或返回 UNKNOWN”。
- **输出格式**：统一使用 `response_format` 或显式 JSON schema，保证结果可直接解析。
- **灰度策略**：可在 `decision.mode` 字段标记 `direct / llm / fallback`，并记录 `confidence` 与 `reason` 以便监控。
- **模型选择**：支持 OpenAI 协议兼容模型（如 Azure OpenAI、火山方舟、通义千问 OpenAI 版等），亦可接入自建服务。
- **成本控制**：对热门问题启用缓存，对低置信度设定重试/回退策略，必要时使用小模型先行判断。

### 4.1 OpenSearch 灰区决策参数速查

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `use_decision` | bool | `true` | 是否在返回结果中包含灰区判定（`direct/gray/reject`）与理由。|
| `use_semantic` | bool | `true` | 是否启用向量召回参与融合打分。|
| `semantic_weight` | float? | `INDEX_CONFIG.default_semantic_weight` | 语义分数在融合中的占比，范围 `[0,1]`。|
| `vector_k` | int | `50` | 语义召回候选数量。|
| `use_llm` | bool | `false` | 是否允许在灰区命中时调用 LLM 进行二次甄选。|
| `llm_topn` | int | `5` | 传入 LLM 的候选数量上限。|

> ⚙️ 当 `use_llm=true` 且最佳候选分数位于 `[gray_low_threshold, pass_threshold)` 区间时，系统会调用 `closed_set_pick` 将若干候选交由 LLM 甄选，并在响应中记录 `decision.mode=llm` 以及 `metadata.llm_*` 字段，便于排查与监控。

---

## 5. 环境变量

```bash
cp .env.example .env
```

- `OPENAI_API_BASE` / `OPENAI_API_KEY` / `OPENAI_MODEL` —— 灰区 LLM 判别所需凭证，留空即可禁用 LLM。
- `PASS_THRESHOLD` / `GRAY_LOW_THRESHOLD` —— 置信度阈值，默认 `0.84 / 0.65`。
- `EMBEDDING_MODEL` / `RERANKER_MODEL` —— 可选：若开启语义召回或 Cross-Encoder 精排。
- `DATA_FILE`、`HNSW_INDEX_PATH`、`TFIDF_CACHE_PATH` —— 本地索引用于混合召回时的默认路径。

---

## 6. 常见问题

- **查询慢怎么办？** → 检查召回权重、限制候选数量、优化提示词长度，并启用异步+超时控制。
- **LLM 结果不稳定？** → 强制 JSON 输出、增加候选信息（系统/部件）帮助模型判定，并在灰区设置更高置信度下限。
- **如何监控？** → 记录每个请求的 `decision.mode`、`confidence`、LLM 时延，与 OpenSearch 打分一起写入日志或监控系统。
- **可以只用 OpenSearch 吗？** → 可以，禁用 LLM 环节即为常规检索服务，灰区判决仍可依赖规则和权重。

---

## 7. 目录速览

- `app/` —— FastAPI 应用、配置与检索逻辑；
- `docs/` —— API 文档、字段映射与 schema 说明；
- `scripts/` —— 数据导入、索引构建、服务管理脚本；
- `tests/` —— 单元/集成测试，包含 OpenSearch 与 LLM 的离线模拟；
- `OpenSearch_Integration_README.md` —— OpenSearch 端详细指引；
- `OPENSEARCH_SYSTEM_COMPLETE.md` —— 完整系统部署笔记。

---

## 8. 许可证

MIT License

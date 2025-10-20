# 评分融合与灰区路由更新说明

本文档详细说明最新一轮对故障匹配服务所做的评分校准、阈值配置以及灰区 LLM 路由等方面的改动，便于后续调试、校验和运营落地。

## 1. 可配置的阈值与权重校准

- `app/config.py` 新增 `Settings.score_calibration_path`，可指向离线生成的 JSON 配置文件。系统启动时会通过 `load_calibration_profile` 自动读取 `pass_threshold`、`gray_low_threshold` 以及融合权重，缺失字段沿用默认值。该文件允许针对不同业务线导出独立的阈值组合。 【F:app/config.py†L34-L69】【F:app/utils/calibration.py†L43-L84】
- 通过 `_apply_env_weight_overrides` 支持 `FUSION_<SOURCE>_WEIGHT` 环境变量热覆盖权重，随后调用 `FusionWeights.normalized()` 使用 `normalize_weight_mapping` 做归一化，确保最终权重之和为 1。 【F:app/config.py†L42-L58】【F:app/utils/calibration.py†L86-L112】

## 2. 评分归一化与融合策略

- `app/utils/calibration.py` 提供 `compute_stats`、`logistic_from_stats` 等工具：在请求级别统计均值方差，并将 BM25、语义余弦、精排分数映射到 [0,1] 区间。极端情况下回退至简单的阈值或经验缩放。 【F:app/utils/calibration.py†L14-L42】【F:app/utils/calibration.py†L86-L112】
- `app/reranker.py` 的 `Reranker.score` 现在对模型 logits 取 `torch.sigmoid`，输出稳定的概率分数，便于和其他信号组合。 【F:app/reranker.py†L18-L26】
- `app/main.py` 在并发获取 HNSW 与 TF-IDF 召回后，针对每个候选计算统计量，并用 `logistic_from_stats` 映射后加权求和，同时根据系统/部件、热度补充知识先验与流行度分。理由字段同步更新，解释归一化后的各项贡献。 【F:app/main.py†L33-L126】

## 3. 灰区决策与 LLM 复核

- 当最高候选得分落在 `gray_low_threshold` 与 `pass_threshold` 之间时，`match` 接口会将前 10 个候选截断后交给 `closed_set_pick`。LLM 仅允许选择给定 ID 或 UNKNOWN，并对理由和置信度做边界约束。 【F:app/main.py†L126-L169】【F:app/llm_router.py†L12-L77】
- `closed_set_pick` 复用基于 `(base_url, api_key)` 的长连 `httpx.AsyncClient`，启用 HTTP/2，减少重复握手；同时对用户查询和候选文本做 `MAX_QUERY_LEN/MAX_CANDIDATE_LEN` 截断，降低提示词成本并控制幻觉风险。 【F:app/llm_router.py†L12-L56】

## 4. OpenSearch 检索融合改造

- OpenSearch 召回阶段对 BM25/语义原始分数同样应用 `compute_stats` + `logistic_from_stats`，在语义关闭时自动回退。最终分数 = 语义/关键词按权重线性融合 + 热度、搜索量微调，并输出可解释的 `why` 标签。 【F:app/opensearch_matcher.py†L207-L323】
- `_generate_base_decision` 会结合最新阈值生成直接通过、灰区、拒绝三种路径。若灰区启用 LLM，则 `match_with_decision_async` 会记录候选数量与返回理由，把 LLM 置信度与候选基础得分求最大值作为最终信心。 【F:app/opensearch_matcher.py†L404-L569】
- 统计接口增加融合权重及语义启用等元数据，方便对线上得分分布进行监控和再校准。 【F:app/opensearch_matcher.py†L324-L348】

## 5. 使用建议

1. **离线校准流程**：在验证集上导出阈值/权重，写入 JSON，部署时通过环境变量 `SCORE_CALIBRATION_PATH` 指定即可生效。
2. **实时监控**：结合 OpenSearch 返回的 `metadata` 以及本地接口的候选 `why` 字段，观察不同请求的分布，及时调整权重。
3. **LLM 成本控制**：灰区窗口越窄，触发 LLM 的请求越少。可按业务需求调节 `gray_low_threshold` 与 `pass_threshold` 差值，或在配置文件里分层设置。

以上调整旨在在保持现有接口不变的情况下，提高多源召回与灰区复核的准确性和可调性。

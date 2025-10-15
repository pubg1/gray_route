# 汽车故障诊断 API 文档

## 概述

这是一个基于FastAPI的汽车故障诊断系统，通过语义搜索、关键词匹配和机器学习重排序来匹配用户描述的故障现象与知识库中的故障案例。

## 基础信息

- **Base URL**: `http://localhost:8000`
- **API版本**: v1
- **响应格式**: JSON
- **编码**: UTF-8

## API 端点

### 1. 健康检查

检查服务是否正常运行。

**端点**: `GET /health`

**响应示例**:
```json
{
  "status": "ok"
}
```

### 2. 故障匹配 (主要API)

根据用户输入的故障描述，返回最匹配的故障案例。

**端点**: `GET /match`

#### 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|--------|------|------|--------|------|
| `q` | string | ✅ | - | 用户查询的故障描述 |
| `system` | string | ❌ | null | 指定系统类型（如"发动机"、"制动"等） |
| `part` | string | ❌ | null | 指定部件名称 |
| `model` | string | ❌ | null | 车型信息 |
| `year` | string | ❌ | null | 年份信息 |
| `topk_vec` | integer | ❌ | 50 | 语义搜索返回的候选数量 |
| `topk_kw` | integer | ❌ | 50 | 关键词搜索返回的候选数量 |
| `topn_return` | integer | ❌ | 3 | 最终返回的结果数量 |

#### 响应格式

```json
{
  "query": "处理后的查询文本",
  "top": [
    {
      "id": "故障案例ID",
      "text": "故障现象描述",
      "system": "故障系统",
      "part": "故障部件",
      "tags": ["标签1", "标签2"],
      "popularity": 流行度分数,
      "bm25_score": BM25分数,
      "cosine": 余弦相似度,
      "rerank_score": 重排序分数,
      "final_score": 最终综合分数,
      "why": ["匹配原因1", "匹配原因2"]
    }
  ],
  "decision": {
    "mode": "决策模式",
    "chosen_id": "推荐的故障案例ID",
    "confidence": 置信度分数
  }
}
```

#### 决策模式说明

- **`direct`**: 直接推荐，置信度高（≥pass_threshold）。
- **`gray`**: 落入灰区，建议人工确认或触发 LLM。
- **`llm`**: LLM 辅助决策，灰区命中后由模型给出最终候选。
- **`fallback`/`reject`**: 兜底模式，置信度较低或未命中。
- **`no_match`**: 未检索到任何候选。

#### 匹配原因说明

- **`语义近`**: 语义相似度高
- **`关键词命中`**: BM25关键词匹配度高
- **`系统一致`**: 指定系统与结果系统完全匹配
- **`部件相近`**: 指定部件与结果部件相关

## 评分算法

最终分数计算公式：
```
final_score = 0.55×rerank_score + 0.20×cosine + 0.10×bm25 + 0.10×kg_prior + 0.05×popularity
```

其中：
- **rerank_score**: 深度学习重排序分数 (55%)
- **cosine**: 语义相似度 (20%)
- **bm25**: 关键词匹配分数 (10%)
- **kg_prior**: 知识图谱先验分数 (10%)
- **popularity**: 流行度分数 (5%)

## 请求示例

### 基础查询
```bash
curl "http://localhost:8000/match?q=刹车发软"
```

### 带系统限定的查询
```bash
curl "http://localhost:8000/match?q=刹车发软&system=制动"
```

### 完整参数查询
```bash
curl "http://localhost:8000/match?q=发动机无法启动&system=发动机&model=宋&year=2019&topn_return=5"
```

## 响应示例

### 成功响应 (直接推荐)
```json
{
  "query": "刹车发软",
  "top": [
    {
      "id": "P0001",
      "text": "制动踏板变软，制动距离变长",
      "system": "制动",
      "part": "制动踏板",
      "tags": ["刹车", "变软", "距离长"],
      "popularity": 162.0,
      "bm25_score": 0.85,
      "cosine": 0.91,
      "rerank_score": 8.12,
      "final_score": 0.90,
      "why": ["语义近", "关键词命中"]
    }
  ],
  "decision": {
    "mode": "direct",
    "chosen_id": "P0001",
    "confidence": 0.90
  }
}
```

### LLM辅助决策响应
```json
{
  "query": "车子有异响",
  "top": [
    {
      "id": "P0006",
      "text": "低速刹车时有金属摩擦异响",
      "system": "制动",
      "part": "制动盘",
      "tags": ["异响", "金属摩擦"],
      "popularity": 197.0,
      "bm25_score": 0.45,
      "cosine": 0.72,
      "rerank_score": 6.8,
      "final_score": 0.65,
      "why": ["语义近"]
    }
  ],
  "decision": {
    "mode": "llm",
    "chosen_id": "P0006",
    "confidence": 0.75,
    "llm": {
      "confidence": 0.72,
      "why": "更符合异响描述",
      "chosen_id": "P0006"
    }
  }
}
```

### 兜底响应
```json
{
  "query": "车子有问题",
  "top": [],
  "decision": {
    "mode": "fallback",
    "chosen_id": null,
    "confidence": 0.0
  }
}
```

### 3. OpenSearch 匹配 (可选灰区决策)

针对已经完成 OpenSearch 导入的环境，使用该端点直接调用远程索引，可启用语义召回、灰区判决和 LLM 精选。

**端点**: `POST /opensearch/match`

#### 请求体参数

| 字段 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `q` | string | ✅ | - | 用户查询文本 |
| `system` | string | ❌ | null | 指定系统过滤 |
| `part` | string | ❌ | null | 指定部件过滤 |
| `vehicletype` | string | ❌ | null | 车型过滤 |
| `fault_code` | string | ❌ | null | 故障码过滤 |
| `size` | integer | ❌ | 10 | 返回候选数量 |
| `use_decision` | bool | ❌ | true | 是否返回灰区决策信息 |
| `use_semantic` | bool | ❌ | true | 是否使用语义向量召回 |
| `semantic_weight` | number | ❌ | 配置默认值 | BM25 与语义融合的权重 |
| `vector_k` | integer | ❌ | 50 | 语义召回候选数量 |
| `use_llm` | bool | ❌ | false | 灰区时是否触发 LLM 精选 |
| `llm_topn` | integer | ❌ | 5 | 传给 LLM 的候选数量上限 |

#### 响应示例

```json
{
  "query": "发动机无法启动",
  "total": 128,
  "top": [
    {
      "id": "DOC-123",
      "text": "发动机点火困难...",
      "system": "发动机",
      "part": "起动系统",
      "bm25_score": 0.74,
      "cosine": 0.68,
      "final_score": 0.73,
      "why": ["语义相关", "系统一致"],
      "sources": ["keyword", "semantic"]
    }
  ],
  "decision": {
    "mode": "llm",
    "chosen_id": "DOC-123",
    "confidence": 0.78,
    "llm": {
      "confidence": 0.76,
      "why": "结合症状描述匹配度最高",
      "chosen_id": "DOC-123"
    }
  },
  "metadata": {
    "semantic_used": true,
    "semantic_weight": 0.6,
    "vector_k": 50,
    "keyword_size": 10,
    "llm_used": true,
    "llm_candidate_count": 5
  }
}
```

当 `use_decision=false` 时，响应中仅包含 `query/top/metadata` 字段，便于纯检索调试。

## 错误处理

### 400 Bad Request
```json
{
  "detail": "查询参数q是必填的"
}
```

### 500 Internal Server Error
```json
{
  "detail": "服务器内部错误"
}
```

## 使用建议

1. **查询优化**: 使用具体的故障描述，如"刹车发软"比"车子有问题"效果更好
2. **系统限定**: 如果知道故障系统，建议使用`system`参数提高精度
3. **置信度判断**: 
   - `confidence ≥ 0.8`: 高置信度，可直接使用
   - `0.6 ≤ confidence < 0.8`: 中等置信度，建议人工确认
   - `confidence < 0.6`: 低置信度，需要更多信息

## 性能指标

- **响应时间**: 通常 < 200ms
- **并发支持**: 支持多用户同时访问
- **准确率**: 在测试集上达到85%+的匹配准确率

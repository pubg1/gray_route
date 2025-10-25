# 故障点检索方案（OpenSearch）

## 目标
- 基于现有 `automotive_cases` 索引中的 `discussion` 字段，检索车辆故障点。
- 支持使用车辆品牌、车型名称、年份、故障码、损坏控制单元与故障现象等输入条件组合检索。
- 暴露独立的 HTTP API 便于系统集成。
- 在原有的可视化页面上提供交互入口展示检索结果。

## 检索策略
1. **关键词/短语约束**
   - 使用 `match` 与 `multi_match` 检索品牌 (`vehiclebrand`)、车型 (`vehicletype`/`topic`) 与控制单元 (`part`/`system`)。
   - 年份字段通过 `match_phrase` 同时尝试 `modelyear`、`spare1`、`spare15`、`year` 等候选字段。
2. **故障现象聚焦**
   - 对 `discussion`、`symptoms`、`text` 等字段给予更高权重，确保故障点描述作为主召回来源。
3. **故障码匹配**
   - 通过 `match_phrase` 对 `faultcode` 与 `spare4` 字段做 OR 匹配，同时保留其他条件。
4. **结果整理**
   - 使用 OpenSearch 高亮结果返回 `discussion` 字段中命中的片段。
   - 汇总车型、系统、部件与置信得分，构造统一结构返回。

## API 设计
- 路径：`POST /opensearch/fault-points`
- 请求体字段：
  | 字段 | 类型 | 说明 |
  | --- | --- | --- |
  | `vehicle_brand` | string? | 车辆品牌，可选 |
  | `vehicle_name` | string? | 车型或车系名称，可选 |
  | `model_year` | string? | 年份，可选 |
  | `fault_code` | string? | 故障码，可选 |
  | `control_unit` | string? | 损坏控制单元，可选 |
  | `symptom` | string? | 故障现象，可选 |
  | `size` | int | 返回数量，默认 5 |
- 响应：
  ```json
  {
    "total": 123,
    "fault_points": [
      {
        "id": "...",
        "score": 4.52,
        "discussion": "原始文本",
        "highlight": "<mark>...</mark>",
        "vehiclebrand": "...",
        "vehicletype": "...",
        "modelyear": "2021",
        "system": "制动系统",
        "part": "ABS 控制模块",
        "faultcode": "C1234"
      }
    ],
    "request": { ... }
  }
  ```
- 若缺少全部条件或检索失败返回 `error` 与 `message` 字段说明。

## 前端交互
- 在现有 `web/index.html` 页面追加“故障点检索”面板：
  - 输入项：品牌、车型、年份、故障码、控制单元、故障现象与返回条数。
  - 点击“检索”调用新 API，并将高亮结果以卡片列表展示；包含得分、车型、系统/部件与故障点描述。
  - “清空”按钮恢复初始提示。

## 集成注意事项
- API 依赖现有 `opensearch_matcher` 连接配置，需确保索引字段与方案中使用的字段一致。
- 若索引中字段名称不同，可在 `_source` 与查询字段列表中调整映射。
- `size` 建议与前端下拉保持同步，避免一次性返回过多结果。

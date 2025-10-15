# OpenSearch 故障现象匹配系统集成

本文档说明如何将 `servicingcase_last.json` 数据集成到 OpenSearch 中，实现按照 README.md 设计的故障现象匹配功能。

## 🎯 系统特性

### 数据保留
- ✅ **保留所有原有字段**：`vehicletype`、`discussion`、`search`、`searchNum` 等
- ✅ **保留原始 ID**：使用 `_id` 字段作为文档 ID，不更改
- ✅ **智能字段扩展**：自动提取 `text`、`system`、`part`、`tags` 等匹配字段

### 故障现象匹配
- ✅ **多字段搜索**：支持故障现象、系统、部件、车型等维度搜索
- ✅ **灰区路由决策**：0.65-0.84 阈值区间的智能决策
- ✅ **混合匹配**：结合本地索引和 OpenSearch 的双重匹配
- ✅ **权重优化**：故障现象权重最高，系统匹配次之

## 🚀 快速开始

### 1. 一键部署
```bash
cd scripts
python deploy_complete_system.py
```

### 2. 手动部署
```bash
# 1. 安装依赖
python install_opensearch_deps.py

# 2. 测试连接
python test_vpc_connection.py

# 3. 导入数据（保留所有字段）
python import_to_opensearch_preserve_fields.py

# 4. 测试系统
python test_system_integration.py

# 5. 启动服务
cd ..
python -m app.main
```

## 📊 数据结构对比

### 原始数据 (servicingcase_last.json)
```json
{
  "_index": "servicingcase_last",
  "_type": "carBag", 
  "_id": "bc7ff60d313f4175a1912bbc4fd7e508",
  "_source": {
    "vehicletype": "CT4",
    "searchNum": 0,
    "discussion": "变速器油型号错误",
    "search": "<div>详细的维修过程...</div>",
    "solution": null,
    "rate": null,
    "vin": null,
    "id": "bc7ff60d313f4175a1912bbc4fd7e508",
    "summary": null,
    "createtime": "2025-07-16 06:52:13",
    "faultcode": null,
    "creatorid": "2b168ca69a774e6aaaa947ffbe1d7423",
    "spare1": "变速器",
    "spare2": "变速器挂D档延迟 / 升档打滑 / 冲击",
    "spare15": "变速器",
    "egon": "变速器油",
    "symptoms": "保养作业后 / 变速器挂D档延迟 / 升档打滑 / 冲击",
    "money": "0",
    "vehiclebrand": "凯迪拉克",
    "topic": "2014款凯迪拉克CT4变速器挂D档延迟 / 升档打滑 / 冲击",
    "searchContent": "详细的故障诊断内容...",
    // ... 所有其他原有字段
  }
}
```

### OpenSearch 存储结构
```json
{
  "_id": "bc7ff60d313f4175a1912bbc4fd7e508",  // 保留原始ID
  "_source": {
    // 🎯 所有原有字段 100% 完全保留
    "vehicletype": "CT4",
    "searchNum": 0,
    "discussion": "变速器油型号错误",
    "search": "<div>详细的维修过程...</div>",
    "solution": null,
    "rate": null,
    "vin": null,
    "id": "bc7ff60d313f4175a1912bbc4fd7e508",
    "summary": null,
    "createtime": "2025-07-16 06:52:13",
    "faultcode": null,
    "creatorid": "2b168ca69a774e6aaaa947ffbe1d7423",
    "spare1": "变速器",
    "spare2": "变速器挂D档延迟 / 升档打滑 / 冲击",
    "spare3": "1",
    "spare4": "X1278 X13567 ",
    "spare5": null,
    "spare6": null,
    "spare10": null,
    "spare11": null,
    "spare12": null,
    "spare15": "变速器",
    "egon": "变速器油",
    "symptoms": "保养作业后 / 变速器挂D档延迟 / 升档打滑 / 冲击",
    "money": "0",
    "vehiclebrand": "凯迪拉克",
    "casestate": null,
    "topic": "2014款凯迪拉克CT4变速器挂D档延迟 / 升档打滑 / 冲击",
    "placement": null,
    "noCode": null,
    "searchContent": "详细的故障诊断内容...",
    
    // ✨ 新增匹配字段（不覆盖原有字段）
    "text": "变速器油型号错误 / 该车变速器挂D档延迟并伴随冲击...",
    "system": "变速箱/传动",
    "part": "变速器控制模块",
    "tags": ["CT4", "维修案例", "故障灯"],
    "popularity": 0,
    "search_content": "清理HTML后的完整内容",
    "import_time": "2025-10-14T23:00:00"
  }
}
```

## 🔍 API 使用

### 1. 健康检查
```bash
curl http://127.0.0.1:8000/health
```

### 2. OpenSearch 故障匹配
```bash
# 基础查询
curl 'http://127.0.0.1:8000/opensearch/match?q=发动机无法启动'

# 系统过滤
curl 'http://127.0.0.1:8000/opensearch/match?q=刹车发软&system=制动'

# 车型过滤
curl 'http://127.0.0.1:8000/opensearch/match?q=故障灯亮&vehicletype=CT4'

# 完整参数
curl 'http://127.0.0.1:8000/opensearch/match?q=变速器挂档冲击&system=变速箱/传动&size=5&use_decision=true'
```

### 3. 混合匹配（推荐）
```bash
# 结合本地索引和OpenSearch
curl 'http://127.0.0.1:8000/match/hybrid?q=发动机启动困难&system=发动机'
```

### 4. 统计信息
```bash
curl http://127.0.0.1:8000/opensearch/stats
```

## 📈 匹配响应格式

### 基础搜索响应
```json
{
  "query": "发动机无法启动",
  "total": 156,
  "top": [
    {
      "id": "bc7ff60d313f4175a1912bbc4fd7e508",
      "text": "发动机无法启动 / HDC / ESP故障灯点亮",
      "system": "发动机",
      "part": "发动机控制模块",
      "tags": ["比亚迪", "启动故障", "故障灯"],
      "vehicletype": "CT4",
      "popularity": 339,
      "score": 8.52,
      "highlight": {
        "text": ["<mark>发动机</mark><mark>无法启动</mark>"]
      }
    }
  ]
}
```

### 灰区路由决策响应
```json
{
  "query": "发动机无法启动",
  "total": 156,
  "top": [...],
  "decision": {
    "mode": "direct",           // direct | gray | reject
    "chosen_id": "bc7ff60d313f4175a1912bbc4fd7e508",
    "confidence": 0.89,
    "reason": "高置信度匹配 (score: 0.890)"
  }
}
```

### 混合匹配响应
```json
{
  "query": "发动机无法启动",
  "local_result": {...},      // 本地索引结果
  "opensearch_result": {...}, // OpenSearch结果
  "recommendation": {
    "use_local": true,
    "use_opensearch": true,
    "confidence_comparison": {
      "local": 0.85,
      "opensearch": 0.89
    }
  }
}
```

## 🛠️ 配置说明

### OpenSearch 配置 (scripts/opensearch_config.py)
```python
OPENSEARCH_CONFIG = {
    'host': 'vpc-carbobo-hty6sxiqn2a5x4dbbiqjtj5reu.us-east-1.es.amazonaws.com',
    'port': 443,
    'username': "chebaobao",
    'password': "Chebaobao*88",
    'use_ssl': True,
    'verify_certs': False,
    'ssl_assert_hostname': False,
    'ssl_show_warn': False,
    'timeout': 30,
}
```

### 匹配阈值配置
```python
# 在 .env 文件中配置
PASS_THRESHOLD=0.84      # 直接通过阈值
GRAY_LOW_THRESHOLD=0.65  # 灰区下限阈值
```

## 🔧 故障排查

### 1. 连接问题
```bash
# 测试VPC端点连接
python scripts/test_vpc_connection.py

# 检查网络和DNS
ping vpc-carbobo-hty6sxiqn2a5x4dbbiqjtj5reu.us-east-1.es.amazonaws.com
```

### 2. 数据导入问题
```bash
# 清除索引重新导入
python scripts/quick_clear_index.py
python scripts/import_to_opensearch_preserve_fields.py

# 检查索引状态
curl -X GET "https://vpc-endpoint:443/automotive_cases/_count" -u username:password
```

### 3. 搜索问题
```bash
# 运行系统测试
python scripts/test_system_integration.py

# 检查索引映射
curl -X GET "https://vpc-endpoint:443/automotive_cases/_mapping" -u username:password
```

## 📊 性能优化

### 1. 搜索优化
- **多字段权重**：`text^3.0`, `discussion^2.5`, `part^2.0`
- **模糊匹配**：`fuzziness: "AUTO"`
- **最小匹配度**：`minimum_should_match: "75%"`

### 2. 索引优化
- **分片配置**：使用AWS默认配置避免冲突
- **字段映射**：针对中文搜索优化
- **缓存策略**：启用查询缓存

### 3. 批量导入优化
- **批次大小**：默认100条/批次
- **并发控制**：避免超时
- **错误处理**：失败重试机制

## 🎯 使用场景

### 1. 精确匹配
```bash
# 查找特定故障
curl 'http://127.0.0.1:8000/opensearch/match?q=发动机无法启动&system=发动机'
```

### 2. 模糊搜索
```bash
# 查找相似问题
curl 'http://127.0.0.1:8000/opensearch/match?q=启动困难'
```

### 3. 系统过滤
```bash
# 按系统分类查找
curl 'http://127.0.0.1:8000/opensearch/match?q=异响&system=发动机'
```

### 4. 车型匹配
```bash
# 特定车型问题
curl 'http://127.0.0.1:8000/opensearch/match?q=故障灯&vehicletype=CT4'
```

## 📝 开发指南

### 1. 扩展搜索字段
在 `app/opensearch_matcher.py` 中修改：
```python
"fields": [
    "text^3.0",           # 故障现象权重最高
    "discussion^2.5",     # 故障点描述
    "search_content^1.0", # 完整内容
    "vehicletype^1.5",    # 车型信息
    "part^2.0"            # 部件信息
]
```

### 2. 调整决策阈值
在 `.env` 文件中：
```bash
PASS_THRESHOLD=0.84      # 提高直接通过门槛
GRAY_LOW_THRESHOLD=0.65  # 降低灰区门槛
```

### 3. 添加新的匹配逻辑
在 `OpenSearchMatcher.match_with_decision()` 中扩展决策逻辑。

## 🔄 数据更新

### 1. 增量更新
```bash
# 导入新数据（不删除现有数据）
python scripts/import_to_opensearch_preserve_fields.py
```

### 2. 全量更新
```bash
# 清除并重新导入
python scripts/quick_clear_index.py
python scripts/import_to_opensearch_preserve_fields.py
```

### 3. 索引重建
```bash
# 完全重置索引结构
python scripts/reset_index.py
python scripts/import_to_opensearch_preserve_fields.py
```

## 📞 技术支持

如遇问题，请检查：
1. OpenSearch VPC 端点连接状态
2. 认证信息是否正确
3. 索引是否存在且包含数据
4. API 服务是否正常运行

运行完整系统测试：
```bash
python scripts/test_system_integration.py
```

## 🎉 总结

本系统成功实现了：
- ✅ 保留 `servicingcase_last.json` 所有原有字段和 ID
- ✅ 智能提取故障现象、系统、部件等匹配信息
- ✅ 实现按照 README.md 设计的灰区路由匹配逻辑
- ✅ 提供完整的 REST API 接口
- ✅ 支持混合匹配（本地+OpenSearch）
- ✅ 提供详细的统计和监控功能

现在可以通过 API 进行高效的故障现象匹配查询！

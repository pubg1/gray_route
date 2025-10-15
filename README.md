# Failure Search with Semantic Retrieval

该项目展示了如何在 OpenSearch 中结合传统文本检索与语义向量检索，针对故障现象进行更精准的匹配。

## 特性

- **KNN 向量字段**：在索引中为故障知识库存储文本向量，支持语义相似度检索。
- **Transformer 语义编码**：默认使用 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` 模型，将标题、描述及关键元数据编码为嵌入向量。
- **混合检索策略**：通过 OpenSearch `script_score` 查询，将关键词得分与向量相似度按照权重组合，实现语义 + 关键词的混合排序。
- **批量入库**：支持批量写入故障案例并自动生成向量。

## 快速开始

1. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

2. 使用示例：

   ```python
   from opensearchpy import OpenSearch
   from failure_search import FailureSearchService

   client = OpenSearch("https://opensearch.example.com", http_auth=("user", "pass"))
   service = FailureSearchService(client=client, index_name="failures")

   service.ensure_index()

   service.index_failure(
       failure_id="F-1001",
       title="风机齿轮箱异响",
       description="机舱震动伴随异响，振动传感器数据异常",
       metadata={"system": "风电", "severity": "S2"},
   )

   result = service.search_failures("机舱异响", size=5)
   for hit in result["hits"]["hits"]:
       print(hit["_source"]["title"], hit["_score"])
   ```

3. 如果需要自定义嵌入模型，可以实现 `BaseEmbedder` 协议并传入 `FailureSearchService(embedder=...)`。

## 测试

执行单元测试：

```bash
pytest
```

## 注意事项

- 第一次使用时将会下载语义模型，请确保具备网络访问。
- 如果生产环境中已经有统一的嵌入服务，可自定义 `embedder` 来复用该服务并避免在应用内下载模型。

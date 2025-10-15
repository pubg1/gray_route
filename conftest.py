"""Pytest fixtures for offline testing without real OpenSearch or HTTP server."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qsl, urlparse

import pytest

try:
    from scripts.opensearch_config import INDEX_CONFIG
except Exception:  # pragma: no cover - config import may fail in exotic envs
    INDEX_CONFIG = {"name": "phenomena-index"}

# --- Sample data used by fixtures -------------------------------------------------------
SAMPLE_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "id": "P001",
        "text": "发动机无法启动，起动机工作但发动机点火失败，需要检查发动机控制系统",
        "system": "发动机",
        "part": "发动机控制",
        "tags": ["发动机", "启动"],
        "vehicletype": "CT4",
        "vehiclebrand": "凯迪拉克",
        "topic": "发动机无法启动",
        "symptoms": "发动机打不着火，仪表警告灯亮",
        "discussion": "车辆冷车状态下多次点火失败",
        "solution": "检查燃油泵及发动机控制模块",
        "egon": "engine",
        "spare1": "",
        "spare2": "",
        "spare4": "P0300",
        "spare15": "",
        "faultcode": "P0300",
        "createtime": "2024-01-01",
        "money": "",
        "popularity": 180,
        "searchNum": 120,
        "rate": 0.92,
    },
    {
        "id": "P002",
        "text": "刹车踏板变软制动力不足，制动距离变长，应检查制动系统",
        "system": "制动",
        "part": "制动总泵",
        "tags": ["制动", "踏板变软"],
        "vehicletype": "唐",
        "vehiclebrand": "比亚迪",
        "topic": "制动踏板发软",
        "symptoms": "刹车踩到底也不减速",
        "discussion": "制动液泄漏导致压力不足",
        "solution": "检查制动液和制动管路",
        "egon": "brake",
        "spare1": "",
        "spare2": "",
        "spare4": "",
        "spare15": "",
        "faultcode": "",
        "createtime": "2024-01-02",
        "money": "",
        "popularity": 150,
        "searchNum": 90,
        "rate": 0.88,
    },
    {
        "id": "P003",
        "text": "变速器换挡顿挫，低速时出现冲击，需要检查变速箱控制逻辑",
        "system": "变速箱/传动",
        "part": "自动变速器",
        "tags": ["变速器", "顿挫"],
        "vehicletype": "Model 3",
        "vehiclebrand": "Tesla",
        "topic": "换挡顿挫",
        "symptoms": "D挡升挡冲击感明显",
        "discussion": "变速箱油老化导致换挡异常",
        "solution": "更换变速箱油并升级程序",
        "egon": "transmission",
        "spare1": "",
        "spare2": "",
        "spare4": "",
        "spare15": "",
        "faultcode": "",
        "createtime": "2024-01-03",
        "money": "",
        "popularity": 95,
        "searchNum": 60,
        "rate": 0.81,
    },
    {
        "id": "P004",
        "text": "空调不制冷，鼓风机正常但出风温度偏高",
        "system": "空调",
        "part": "制冷系统",
        "tags": ["空调", "不制冷"],
        "vehicletype": "雅阁",
        "vehiclebrand": "本田",
        "topic": "空调系统故障",
        "symptoms": "开启空调后车内温度无法下降",
        "discussion": "制冷剂泄漏导致制冷效果差",
        "solution": "检查空调管路并补充制冷剂",
        "egon": "ac",
        "spare1": "",
        "spare2": "",
        "spare4": "",
        "spare15": "",
        "faultcode": "",
        "createtime": "2024-01-04",
        "money": "",
        "popularity": 110,
        "searchNum": 70,
        "rate": 0.86,
    },
]


# --- Fake OpenSearch client -------------------------------------------------------------
@dataclass
class _FakeIndicesClient:
    index_name: str

    def exists(self, index: str) -> bool:
        return index == self.index_name

    def stats(self, index: str) -> Dict[str, Any]:
        docs_count = len(SAMPLE_DOCUMENTS)
        size_bytes = docs_count * 2048
        return {
            "indices": {
                index: {
                    "total": {
                        "docs": {"count": docs_count},
                        "store": {"size_in_bytes": size_bytes},
                    }
                }
            }
        }


class FakeOpenSearchClient:
    def __init__(self, index_name: str):
        self._index_name = index_name
        self.indices = _FakeIndicesClient(index_name)

    # --- helpers ------------------------------------------------------------------
    @staticmethod
    def _score_document(doc: Dict[str, Any], query: str) -> float:
        terms = [t for t in query.replace("，", " ").replace(",", " ").split() if t]
        if not terms:
            return 0.0
        text = " ".join([doc.get("text", ""), doc.get("symptoms", ""), doc.get("discussion", "")])
        matches = sum(1 for term in terms if term in text)
        return matches / len(terms)

    def info(self) -> Dict[str, Any]:
        return {
            "version": {"number": "2.11.0"},
            "cluster_name": "fake-opensearch",
        }

    def count(self, index: str) -> Dict[str, int]:
        if index != self._index_name:
            return {"count": 0}
        return {"count": len(SAMPLE_DOCUMENTS)}

    def search(self, index: str, body: Dict[str, Any], size: int | None = None) -> Dict[str, Any]:
        if index != self._index_name:
            raise ValueError(f"Unknown index: {index}")

        # Aggregation request
        if body.get("size") == 0 and "aggs" in body:
            buckets = []
            counts: Dict[str, int] = {}
            for doc in SAMPLE_DOCUMENTS:
                veh = doc.get("vehicletype", "UNKNOWN") or "UNKNOWN"
                counts[veh] = counts.get(veh, 0) + 1
            for veh, count in counts.items():
                buckets.append({"key": veh, "doc_count": count})
            return {"aggregations": {"vehicle_types": {"buckets": buckets}}}

        limit = size or body.get("size") or 10
        query = body.get("query", {})

        if "multi_match" in query.get("bool", {}).get("must", {}):
            search_text = query["bool"]["must"]["multi_match"].get("query", "")
        elif "match_all" in query:
            search_text = ""
        else:
            search_text = body.get("knn", {}).get("query_vector", "")

        results: List[Tuple[Dict[str, Any], float]] = []
        for doc in SAMPLE_DOCUMENTS:
            score = self._score_document(doc, search_text)
            if score > 0 or not search_text:
                results.append((doc, score))

        # fallback: if nothing matches give slight scores
        if not results and SAMPLE_DOCUMENTS:
            results = [(SAMPLE_DOCUMENTS[0], 0.1)]

        results.sort(key=lambda item: item[1], reverse=True)

        hits = []
        for doc, score in results[:limit]:
            highlight = {}
            if search_text and score > 0:
                highlight = {
                    "text": [doc["text"].replace(search_text, f"<mark>{search_text}</mark>")],
                }
            hits.append(
                {
                    "_id": doc["id"],
                    "_score": max(score, 0.01),
                    "_source": doc,
                    "highlight": highlight,
                }
            )

        return {
            "hits": {
                "total": {"value": len(results)},
                "hits": hits,
            }
        }


# --- Fixtures ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def client() -> FakeOpenSearchClient:
    """Provide a fake OpenSearch client for tests that expect one."""
    index_name = INDEX_CONFIG.get("name", "phenomena-index")
    return FakeOpenSearchClient(index_name)


@pytest.fixture(scope="session")
def index_name() -> str:
    return INDEX_CONFIG.get("name", "phenomena-index")


@pytest.fixture(scope="session")
def base_url() -> str:
    """Base URL used by high level HTTP tests."""
    return "http://127.0.0.1:8000"


@pytest.fixture(scope="session")
def query() -> str:
    return "发动机无法启动"


class _FakeResponse:
    def __init__(self, status_code: int, payload: Dict[str, Any]):
        self.status_code = status_code
        self._payload = payload
        self.headers = {"content-type": "application/json"}

    def json(self) -> Dict[str, Any]:
        return self._payload

    @property
    def text(self) -> str:
        return json.dumps(self._payload, ensure_ascii=False)


def _build_search_results(q: str, size: int = 3) -> List[Dict[str, Any]]:
    docs_with_scores = [
        (doc, FakeOpenSearchClient._score_document(doc, q)) for doc in SAMPLE_DOCUMENTS
    ]
    docs_with_scores.sort(key=lambda item: item[1], reverse=True)

    results: List[Dict[str, Any]] = []
    for doc, score in docs_with_scores[:size]:
        results.append(
            {
                "id": doc["id"],
                "text": doc["text"],
                "system": doc["system"],
                "part": doc["part"],
                "tags": doc.get("tags", []),
                "vehicletype": doc.get("vehicletype", ""),
                "vehiclebrand": doc.get("vehiclebrand", ""),
                "final_score": round(min(1.0, 0.7 + score * 0.3), 3),
                "rerank_score": round(min(1.0, 0.6 + score * 0.4), 3),
                "bm25_score": round(min(1.0, score + 0.1), 3),
                "cosine": round(min(1.0, score + 0.2), 3),
                "popularity": doc.get("popularity", 0),
                "why": ["语义相关"] if score > 0 else ["文本匹配"],
            }
        )
    return results


def _make_decision(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {"mode": "no_match", "chosen_id": None, "confidence": 0.0}
    top = results[0]
    confidence = float(top.get("final_score", 0.0))
    if confidence >= 0.84:
        return {"mode": "direct", "chosen_id": top["id"], "confidence": confidence}
    if confidence >= 0.65:
        return {"mode": "llm", "chosen_id": top["id"], "confidence": confidence}
    return {"mode": "fallback", "chosen_id": None, "confidence": confidence}


@pytest.fixture(autouse=True)
def _patch_requests(monkeypatch: pytest.MonkeyPatch, base_url: str) -> None:
    """Patch requests API to avoid real network calls during tests."""
    import requests

    def _dispatch(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        parsed = urlparse(url)
        base_netloc = urlparse(base_url).netloc
        if parsed.netloc not in {base_netloc, "localhost:8000"}:
            raise RuntimeError(f"Unexpected URL in tests: {url}")

        path = parsed.path or "/"
        params = dict(parse_qsl(parsed.query))
        if "params" in kwargs and isinstance(kwargs["params"], dict):
            params.update(kwargs["params"])

        if method == "GET" and path == "/health":
            payload = {
                "status": "ok",
                "opensearch_available": True,
                "semantic_available": True,
                "data_sources": ["local_hnsw", "local_tfidf", "opensearch"],
            }
            return _FakeResponse(200, payload)

        if method == "GET" and path == "/match":
            q = params.get("q", "")
            size = int(params.get("topn_return", 3))
            results = _build_search_results(q, size)
            payload = {
                "query": q,
                "top": results,
                "decision": _make_decision(results),
            }
            return _FakeResponse(200, payload)

        if method == "POST" and path == "/opensearch/match":
            body = kwargs.get("json") or {}
            q = body.get("q", "")
            size = int(body.get("size", 10))
            results = _build_search_results(q, size)
            payload = {
                "query": q,
                "total": len(results),
                "top": results,
                "decision": _make_decision(results),
                "metadata": {
                    "semantic_used": True,
                    "semantic_weight": 0.6,
                    "vector_k": 50,
                    "keyword_size": size,
                },
            }
            return _FakeResponse(200, payload)

        # default fallback
        return _FakeResponse(404, {"error": f"unknown path: {path}"})

    def _get(url: str, **kwargs: Any) -> _FakeResponse:
        return _dispatch("GET", url, **kwargs)

    def _post(url: str, **kwargs: Any) -> _FakeResponse:
        return _dispatch("POST", url, **kwargs)

    def _session_request(self: Any, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        return _dispatch(method.upper(), url, **kwargs)

    monkeypatch.setattr(requests, "get", _get)
    monkeypatch.setattr(requests, "post", _post)
    monkeypatch.setattr(requests.Session, "request", _session_request)
    monkeypatch.setattr(requests.Session, "get", lambda self, url, **kw: _dispatch("GET", url, **kw))
    monkeypatch.setattr(requests.Session, "post", lambda self, url, **kw: _dispatch("POST", url, **kw))

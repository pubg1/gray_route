import json
from typing import Dict, List, Tuple

import httpx

from .config import get_settings

SYSTEM_PROMPT = (
    "你是“故障现象归一化器”。只能从候选中选择一个 ID，或返回 UNKNOWN。"
    "仅输出 JSON：{\"chosen_id\":\"<ID或UNKNOWN>\", \"confidence\":0-1, \"why\":\"<不超过20字>\"}"
)

MAX_QUERY_LEN = 200
MAX_CANDIDATE_LEN = 200

_client_pool: Dict[Tuple[str, str], httpx.AsyncClient] = {}


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


async def _get_client(base_url: str, api_key: str) -> httpx.AsyncClient:
    key = (base_url, api_key)
    client = _client_pool.get(key)
    if client is None:
        timeout = httpx.Timeout(20.0)
        client = httpx.AsyncClient(base_url=base_url, timeout=timeout, http2=True)
        _client_pool[key] = client
    return client


async def closed_set_pick(query: str, candidates: List[Dict[str, str]]) -> Dict:
    s = get_settings()
    if not s.openai_api_key or not s.openai_model or not s.openai_api_base:
        return {"chosen_id": "UNKNOWN", "confidence": 0.0, "why": "llm not configured"}
    trimmed_query = _truncate(query, MAX_QUERY_LEN)
    sanitized_candidates = []
    for idx, cand in enumerate(candidates, 1):
        cand_id = str(cand.get("id", "")).strip()
        text = _truncate(str(cand.get("text", "")), MAX_CANDIDATE_LEN)
        sanitized_candidates.append((idx, cand_id, text))
    cand_text = "\n".join(
        [f"{i}) {{id:\"{cid}\", text:\"{txt}\"}}" for i, cid, txt in sanitized_candidates]
    )
    user_prompt = f"用户输入：{trimmed_query}\n\n候选(仅可选其一)：\n{cand_text}\n"
    payload = {
        "model": s.openai_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {s.openai_api_key}"}
    try:
        client = await _get_client(s.openai_api_base, s.openai_api_key)
        response = await client.post("/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        out = json.loads(content)
        cand_ids = {c[1] for c in sanitized_candidates}
        chosen_id = out.get("chosen_id")
        if chosen_id not in cand_ids and chosen_id != "UNKNOWN":
            out["chosen_id"] = "UNKNOWN"
            out["confidence"] = 0.0
        try:
            out["confidence"] = max(0.0, min(1.0, float(out.get("confidence", 0.0))))
        except (TypeError, ValueError):
            out["confidence"] = 0.0
        if "why" in out and isinstance(out["why"], str):
            out["why"] = _truncate(out["why"], 20)
        else:
            out["why"] = ""
        return out
    except Exception:
        return {"chosen_id": "UNKNOWN", "confidence": 0.0, "why": "llm error"}

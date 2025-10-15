
import json, httpx
from typing import List, Dict
from .config import get_settings
SYSTEM_PROMPT = ("你是“故障现象归一化器”。只能从候选中选择一个 ID，或返回 UNKNOWN。"
                 "仅输出 JSON：{\"chosen_id\":\"<ID或UNKNOWN>\", \"confidence\":0-1, \"why\":\"<不超过20字>\"}")
async def closed_set_pick(query: str, candidates: List[Dict[str, str]]) -> Dict:
    s = get_settings()
    if not s.openai_api_key or not s.openai_model or not s.openai_api_base:
        return {"chosen_id": "UNKNOWN", "confidence": 0.0, "why": "llm not configured"}
    cand_text = "\n".join([f"{i+1}) {{id:\"{c['id']}\", text:\"{c['text']}\"}}" for i, c in enumerate(candidates)])
    user_prompt = f"用户输入：{query}\n\n候选(仅可选其一)：\n{cand_text}\n"
    payload = {"model": s.openai_model, "messages": [{"role":"system","content": SYSTEM_PROMPT},{"role":"user","content": user_prompt}], "temperature": 0, "response_format": {"type": "json_object"}}
    headers = {"Authorization": f"Bearer {s.openai_api_key}"}
    async with httpx.AsyncClient(base_url=s.openai_api_base, timeout=20) as client:
        try:
            r = await client.post("/v1/chat/completions", json=payload, headers=headers); r.raise_for_status()
            data = r.json(); content = data["choices"][0]["message"]["content"]
            out = json.loads(content); cand_ids = {c['id'] for c in candidates}
            if out.get("chosen_id") not in cand_ids and out.get("chosen_id") != "UNKNOWN":
                out["chosen_id"] = "UNKNOWN"; out["confidence"] = 0.0
            return out
        except Exception:
            return {"chosen_id": "UNKNOWN", "confidence": 0.0, "why": "llm error"}

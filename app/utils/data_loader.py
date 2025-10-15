# app/utils/data_loader.py
import json, csv, os, io

def iter_records(path: str):
    # 先读一点头部来判断类型
    with open(path, "r", encoding="utf-8-sig") as f:
        head = f.read(2048)
        f.seek(0)

        stripped = head.lstrip()
        # JSON 数组
        if stripped.startswith("["):
            data = json.load(f)
            for obj in data:
                yield obj
            return

        # CSV（简单探测：第一行包含逗号且含 id/text）
        first = f.readline()
        f.seek(0)
        if "," in first and ("id" in first.lower() or "text" in first.lower()):
            reader = csv.DictReader(f)
            for row in reader:
                yield {
                    "id": row.get("id") or row.get("ID") or row.get("编号") or "",
                    "text": row.get("text") or row.get("故障现象") or row.get("描述") or "",
                    "system": row.get("system") or row.get("系统") or "",
                    "part": row.get("part") or row.get("部件") or "",
                    "tags": [t.strip() for t in (row.get("tags") or "").split("|") if t.strip()],
                    "popularity": float(row.get("popularity") or row.get("热度") or 0) or 0.0,
                }
            return

        # 默认按 JSONL 逐行解析
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                preview = line[:120]
                raise ValueError(f"{path}:{lineno} 不是合法 JSON/JSONL：{e.msg} (列 {e.colno})；示例：{preview}")

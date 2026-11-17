import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    action: str
    text: str
    chunk_ids: list[str]


def parse_decision(raw: str) -> Decision | None:
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    action = data.get("action")
    text = data.get("text") or ""
    chunk_ids = data.get("chunk_ids") or []
    if action not in {"answer", "refuse"}:
        return None
    if not isinstance(text, str) or not isinstance(chunk_ids, list):
        return None
    if not all(isinstance(item, str) for item in chunk_ids):
        return None
    return Decision(action=action, text=text.strip(), chunk_ids=chunk_ids)

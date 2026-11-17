import hashlib
import re
from pathlib import Path


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def chunk_id(path: str, ordinal: int, digest: str) -> str:
    raw = f"{path}\n{ordinal}\n{digest}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def split_text(text: str, limit: int = 1200) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= limit:
        return [cleaned]
    parts: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + limit)
        if end < len(cleaned):
            break_at = cleaned.rfind("\n", start, end)
            if break_at > start + limit // 2:
                end = break_at
        piece = cleaned[start:end].strip()
        if piece:
            parts.append(piece)
        if end == start:
            end = start + limit
        start = end
    return parts


def fence(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cache_key(question: str, fingerprint: str) -> str:
    return hashlib.sha256(f"{question}\n{fingerprint}".encode()).hexdigest()

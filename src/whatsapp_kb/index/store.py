import fcntl
import json
import sqlite3
import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from whatsapp_kb.textutil import chunk_id, content_hash
from whatsapp_kb.types import PendingItem


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class StoredChunk:
    id: str
    path: str
    text: str
    content_hash: str
    vector: list[float]


class Index:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL").fetchone()
        self._db.execute("PRAGMA busy_timeout=5000").fetchone()
        self._setup()

    def _setup(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS files (
              path TEXT PRIMARY KEY,
              file_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chunks (
              id TEXT PRIMARY KEY,
              path TEXT NOT NULL,
              ordinal INTEGER NOT NULL,
              text TEXT NOT NULL,
              content_hash TEXT NOT NULL,
              embedding TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
              wamid TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS pauses (
              sender TEXT PRIMARY KEY,
              until TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pending (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              sender TEXT NOT NULL,
              question TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cache (
              key TEXT PRIMARY KEY,
              text TEXT NOT NULL,
              handed_off INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rates (
              sender TEXT PRIMARY KEY,
              window_start TEXT NOT NULL,
              count INTEGER NOT NULL
            );
            """
        )
        self._prune()

    def _prune(self) -> None:
        now = _now()
        with self._lock:
            try:
                self._db.execute("DELETE FROM pauses WHERE until <= ?", (now.isoformat(),))
                cutoff = (now - timedelta(seconds=120)).isoformat()
                self._db.execute("DELETE FROM rates WHERE window_start <= ?", (cutoff,))
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise

    def _write(self, operation: Callable[[], None]) -> None:
        with self._lock:
            try:
                operation()
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise

    @contextmanager
    def reindex_lock(self):
        lock_path = self.path.with_name(self.path.name + ".lock")
        handle = lock_path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def meta(self, key: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_meta(self, key: str, value: str) -> None:
        def operation() -> None:
            self._db.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

        self._write(operation)

    def forget_files(self) -> None:
        def operation() -> None:
            self._db.execute("DELETE FROM chunks")
            self._db.execute("DELETE FROM files")

        self._write(operation)

    def clear_cache(self) -> None:
        def operation() -> None:
            self._db.execute("DELETE FROM cache")

        self._write(operation)

    def file_hash(self, path: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT file_hash FROM files WHERE path = ?", (path,)).fetchone()
        return None if row is None else str(row["file_hash"])

    def hashes_for(self, path: str) -> dict[str, list[float]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT content_hash, embedding FROM chunks WHERE path = ?",
                (path,),
            ).fetchall()
        found: dict[str, list[float]] = {}
        for row in rows:
            found[str(row["content_hash"])] = json.loads(row["embedding"])
        return found

    def replace_file(self, path: str, file_hash: str, rows: list[tuple[str, str, str, list[float]]]) -> None:
        def operation() -> None:
            self._db.execute("DELETE FROM chunks WHERE path = ?", (path,))
            self._db.execute(
                "INSERT INTO files (path, file_hash) VALUES (?, ?) "
                "ON CONFLICT(path) DO UPDATE SET file_hash = excluded.file_hash",
                (path, file_hash),
            )
            self._db.executemany(
                "INSERT INTO chunks (id, path, ordinal, text, content_hash, embedding) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (chunk, path, ordinal, text, digest, json.dumps(vector))
                    for ordinal, (chunk, text, digest, vector) in enumerate(rows)
                ],
            )

        self._write(operation)

    def drop_missing(self, keep: set[str]) -> None:
        def operation() -> None:
            rows = self._db.execute("SELECT path FROM files").fetchall()
            stale = [str(row["path"]) for row in rows if str(row["path"]) not in keep]
            for path in stale:
                self._db.execute("DELETE FROM chunks WHERE path = ?", (path,))
                self._db.execute("DELETE FROM files WHERE path = ?", (path,))

        self._write(operation)

    def all_chunks(self) -> list[StoredChunk]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, path, text, content_hash, embedding FROM chunks"
            ).fetchall()
        return [
            StoredChunk(
                id=str(row["id"]),
                path=str(row["path"]),
                text=str(row["text"]),
                content_hash=str(row["content_hash"]),
                vector=json.loads(row["embedding"]),
            )
            for row in rows
        ]

    def count(self) -> int:
        with self._lock:
            row = self._db.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
        return int(row["n"])

    def fingerprint(self) -> str:
        with self._lock:
            rows = self._db.execute("SELECT path, file_hash FROM files ORDER BY path").fetchall()
        payload = "\n".join(f"{row['path']}:{row['file_hash']}" for row in rows)
        return content_hash(payload)

    def remember(self, wamid: str) -> bool:
        with self._lock:
            try:
                self._db.execute("INSERT INTO messages (wamid) VALUES (?)", (wamid,))
                self._db.commit()
            except sqlite3.IntegrityError:
                self._db.rollback()
                return False
            except Exception:
                self._db.rollback()
                raise
        return True

    def paused(self, sender: str) -> bool:
        with self._lock:
            row = self._db.execute("SELECT until FROM pauses WHERE sender = ?", (sender,)).fetchone()
        if row is None:
            return False
        until = datetime.fromisoformat(str(row["until"]))
        if until <= _now():
            return False
        return True

    def pause(self, sender: str, hours: float) -> None:
        until = (_now() + timedelta(hours=hours)).isoformat()

        def operation() -> None:
            self._db.execute(
                "INSERT INTO pauses (sender, until) VALUES (?, ?) "
                "ON CONFLICT(sender) DO UPDATE SET until = excluded.until",
                (sender, until),
            )

        self._write(operation)

    def unpause(self, sender: str) -> None:
        def operation() -> None:
            self._db.execute("DELETE FROM pauses WHERE sender = ?", (sender,))

        self._write(operation)

    def add_pending(self, sender: str, question: str) -> None:
        def operation() -> None:
            existing = self._db.execute(
                "SELECT id FROM pending WHERE sender = ? AND question = ?",
                (sender, question),
            ).fetchone()
            if existing is not None:
                return
            self._db.execute(
                "INSERT INTO pending (sender, question, created_at) VALUES (?, ?, ?)",
                (sender, question, _now().isoformat()),
            )

        self._write(operation)

    def resolve_pending(self, item_id: int) -> bool:
        removed = False

        def operation() -> None:
            nonlocal removed
            cursor = self._db.execute("DELETE FROM pending WHERE id = ?", (item_id,))
            removed = cursor.rowcount > 0

        self._write(operation)
        return removed

    def list_pending(self) -> list[PendingItem]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, sender, question, created_at FROM pending ORDER BY id DESC"
            ).fetchall()
        return [
            PendingItem(
                id=int(row["id"]),
                sender=str(row["sender"]),
                question=str(row["question"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def cache_get(self, key: str) -> tuple[str, bool] | None:
        with self._lock:
            row = self._db.execute("SELECT text, handed_off FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return str(row["text"]), bool(row["handed_off"])

    def cache_put(self, key: str, text: str, handed_off: bool) -> None:
        def operation() -> None:
            self._db.execute(
                "INSERT INTO cache (key, text, handed_off) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET text = excluded.text, handed_off = excluded.handed_off",
                (key, text, int(handed_off)),
            )

        self._write(operation)

    def allow(self, sender: str, limit: int) -> bool:
        if limit <= 0:
            return False
        now = _now()
        allowed = False

        def operation() -> None:
            nonlocal allowed
            row = self._db.execute(
                "SELECT window_start, count FROM rates WHERE sender = ?",
                (sender,),
            ).fetchone()
            if row is None:
                self._db.execute(
                    "INSERT INTO rates (sender, window_start, count) VALUES (?, ?, 1)",
                    (sender, now.isoformat()),
                )
                allowed = True
                return
            start = datetime.fromisoformat(str(row["window_start"]))
            count = int(row["count"])
            if (now - start).total_seconds() >= 60:
                self._db.execute(
                    "UPDATE rates SET window_start = ?, count = 1 WHERE sender = ?",
                    (now.isoformat(), sender),
                )
                allowed = True
                return
            if count >= limit:
                allowed = False
                return
            self._db.execute(
                "UPDATE rates SET count = ? WHERE sender = ?",
                (count + 1, sender),
            )
            allowed = True

        self._write(operation)
        return allowed

    def close(self) -> None:
        with self._lock:
            self._db.close()


def prepare_rows(
    path: str,
    texts: list[str],
    reusable: dict[str, list[float]],
    embed_passages,
) -> list[tuple[str, str, str, list[float]]]:
    pending: list[tuple[int, str, str]] = []
    rows: list[tuple[str, str, str, list[float]] | None] = []
    for ordinal, text in enumerate(texts):
        digest = content_hash(text)
        identifier = chunk_id(path, ordinal, digest)
        cached = reusable.get(digest)
        if cached is None:
            pending.append((ordinal, text, digest))
            rows.append(None)
        else:
            rows.append((identifier, text, digest, cached))
    if pending:
        vectors = embed_passages([text for _, text, _ in pending])
        if len(vectors) != len(pending):
            raise RuntimeError("El embedder devolvió una cantidad distinta de vectores")
        for (ordinal, text, digest), vector in zip(pending, vectors):
            rows[ordinal] = (chunk_id(path, ordinal, digest), text, digest, vector)
    return [row for row in rows if row is not None]

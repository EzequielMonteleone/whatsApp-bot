import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from whatsapp_kb.config import Settings
from whatsapp_kb.index.embeddings import passage_input, query_input
from whatsapp_kb.index.retrieve import pack_hits
from whatsapp_kb.index.vectors import cosine_distance
from whatsapp_kb.types import Hit


def test_prefixes_match_the_index_convention():
    assert passage_input("hola") == "passage: hola"
    assert query_input("hola") == "query: hola"
    assert passage_input("hola", "") == "hola"


def test_settings_read_the_model_names(tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("hola", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(
        """
name: Casa
scope: Archivos
embeddings:
  model: BAAI/bge-small-en-v1.5
  passage_prefix: ""
  query_prefix: ""
cursor:
  model: auto
""",
        encoding="utf-8",
    )
    settings = Settings.load(config)
    assert settings.embedding_model == "BAAI/bge-small-en-v1.5"
    assert settings.passage_prefix == ""
    assert settings.query_prefix == ""
    assert settings.model == "auto"
    assert settings.provider == "cursor"


def test_dotenv_does_not_override_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "from-env")
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    (tmp_path / ".env").write_text(
        'WHATSAPP_TOKEN=from-file\nCURSOR_API_KEY="from-file"\n',
        encoding="utf-8",
    )
    (tmp_path / "prompt.md").write_text("hola", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("name: Casa\nscope: Archivos\n", encoding="utf-8")
    settings = Settings.load(tmp_path / "config.yaml")
    assert settings.whatsapp_token == "from-env"
    assert settings.api_key() == "from-file"


def test_absurd_config_is_rejected(tmp_path):
    (tmp_path / "prompt.md").write_text("hola", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text("name: Casa\nscope: Archivos\nserver:\n  port: 99999\n", encoding="utf-8")
    with pytest.raises(ValueError, match="port"):
        Settings.load(config)
    config.write_text("name: Casa\nscope: Archivos\nlimits:\n  rate_per_minute: -1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="rate_per_minute"):
        Settings.load(config)


def test_replace_file_rolls_back(tmp_path):
    from whatsapp_kb.index.store import Index

    index = Index(tmp_path / "index.db")
    index.replace_file("a", "hash1", [("id1", "texto", "d1", [1.0])])
    with pytest.raises(sqlite3.IntegrityError):
        index.replace_file(
            "a",
            "hash2",
            [("id1", "nuevo", "d2", [1.0]), ("id1", "dup", "d3", [1.0])],
        )
    assert index.file_hash("a") == "hash1"
    assert [chunk.text for chunk in index.all_chunks()] == ["texto"]


def test_reopen_drops_expired_pauses_and_rates(tmp_path):
    from whatsapp_kb.index.store import Index

    path = tmp_path / "index.db"
    index = Index(path)
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    index.pause("549", 1)

    def rewrite() -> None:
        index._db.execute("UPDATE pauses SET until = ?", (old,))
        index._db.execute(
            "INSERT INTO rates (sender, window_start, count) VALUES (?, ?, 1)",
            ("549", old),
        )

    index._write(rewrite)
    index.close()
    reopened = Index(path)
    assert reopened._db.execute("SELECT sender FROM pauses").fetchone() is None
    assert reopened._db.execute("SELECT sender FROM rates").fetchone() is None
    reopened.close()


def test_cosine_distance_is_zero_for_the_same_vector():
    assert cosine_distance([1.0, 0.0], [2.0, 0.0]) == 0
    assert cosine_distance([1.0, 0.0], [0.0, 1.0]) == 1


def test_pack_hits_keeps_the_nearest_within_the_budget():
    hits = [
        Hit(id="far", path="f", text="lejos", distance=0.9),
        Hit(id="near", path="n", text="x" * 200, distance=0.1),
        Hit(id="mid", path="m", text="medio", distance=0.2),
    ]
    chosen = pack_hits(hits, top_k=2, max_context_tokens=30)
    assert [hit.id for hit in chosen] == ["near"]
    assert len(chosen[0].text) == 120

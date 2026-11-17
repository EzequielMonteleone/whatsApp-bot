import logging
from pathlib import Path

from whatsapp_kb.answer import default_guards
from whatsapp_kb.answer.cursor_model import CursorResponder, ModelError
from whatsapp_kb.answer.responder import build_responder
from whatsapp_kb.answer.decision import parse_decision
from whatsapp_kb.answer.prompting import build_prompt
from whatsapp_kb.config import Settings
from whatsapp_kb.index.embeddings import FastEmbedder
from whatsapp_kb.index.retrieve import pack_hits
from whatsapp_kb.index.store import Index, prepare_rows
from whatsapp_kb.index.vectors import cosine_distance
from whatsapp_kb.sources import default_sources
from whatsapp_kb.textutil import cache_key, file_digest, normalize
from whatsapp_kb.types import Hit, Outcome, PendingItem

logger = logging.getLogger("whatsapp_kb")


class KnowledgeBot:
    def __init__(
        self,
        settings: Settings,
        *,
        embedder=None,
        responder=None,
        sources=None,
        guards=None,
    ) -> None:
        self.settings = settings
        self.embedder = embedder or FastEmbedder(
            model_name=settings.embedding_model,
            passage_prefix=settings.passage_prefix,
            query_prefix=settings.query_prefix,
        )
        self.sources = sources if sources is not None else default_sources()
        self.guards = guards if guards is not None else default_guards()
        self.index = Index(settings.data_dir / "index.db")
        self.responder = responder or build_responder(settings)

    @classmethod
    def open(cls, path: str | Path, **kwargs) -> "KnowledgeBot":
        return cls(Settings.load(path), **kwargs)

    def reindex(self, *, force: bool = False) -> int:
        directory = self.settings.knowledge_dir
        if not directory.is_dir():
            raise FileNotFoundError(f"No existe la carpeta de archivos: {directory}")
        with self.index.reindex_lock():
            return self._reindex(directory, force=force)

    def _reindex(self, directory: Path, *, force: bool) -> int:
        transcribe_on = isinstance(self.responder, CursorResponder) and bool(self.settings.api_key())
        transcribe_flag = "on" if transcribe_on else "off"
        rebuild = (
            force
            or self.index.meta("embedding") != self.settings.embedding_id
            or self.index.meta("transcription") != transcribe_flag
        )
        if rebuild:
            self.index.forget_files()
            self.index.clear_cache()
        transcribe = self.responder.transcribe_page if transcribe_on else None
        keep: set[str] = set()
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.name.startswith(".") or path.name.startswith("~$"):
                continue
            source = self._source_for(path)
            if source is None:
                continue
            location = str(path.resolve())
            try:
                digest = file_digest(path)
                if self.index.file_hash(location) == digest:
                    keep.add(location)
                    continue
                texts = source.load(path, transcribe=transcribe)
                rows = prepare_rows(location, texts, self.index.hashes_for(location), self.embedder.embed_passages)
                self.index.replace_file(location, digest, rows)
                keep.add(location)
            except Exception:
                logger.exception("no se pudo indexar %s", path)
                if self.index.file_hash(location):
                    keep.add(location)
        self.index.drop_missing(keep)
        self.index.set_meta("embedding", self.settings.embedding_id)
        self.index.set_meta("transcription", transcribe_flag)
        return self.index.count()

    def answer(self, question: str, *, sender: str | None = None) -> Outcome:
        cleaned = normalize(question)[: self.settings.max_incoming_chars]
        who = sender or ""
        if not cleaned:
            return Outcome(self.settings.refusal, handed_off=False)
        if who and self.index.paused(who):
            return Outcome("", handed_off=True, skipped=True)
        if who and not self.index.allow(who, self.settings.rate_per_minute):
            return Outcome(self.settings.refusal, handed_off=False)
        stored = self.index.cache_get(self._cache_key(cleaned))
        if stored is not None:
            text, handed_off = stored
            return Outcome(text, handed_off=handed_off, cached=True)
        hits = self._search(cleaned)
        if not hits or hits[0].distance > self.settings.max_distance:
            return self._handoff(who, cleaned)
        shown = pack_hits(
            [hit for hit in hits if hit.distance <= self.settings.max_distance],
            top_k=self.settings.top_k,
            max_context_tokens=self.settings.max_context_tokens,
        )
        if not shown:
            return self._handoff(who, cleaned)
        prompt = build_prompt(self.settings.system_prompt(), shown, cleaned)
        try:
            raw = self.responder.complete(prompt)
        except ModelError as exc:
            logger.error("el modelo no pudo responder: %s", exc)
            return Outcome(self.settings.unavailable, handed_off=False)
        decision = parse_decision(raw)
        if decision is None or decision.action != "answer":
            return self._handoff(who, cleaned)
        by_id = {hit.id: hit for hit in shown}
        if not decision.chunk_ids or any(item not in by_id for item in decision.chunk_ids):
            return self._handoff(who, cleaned)
        cited = "\n".join(by_id[item].text for item in decision.chunk_ids)
        if any(not guard.allow(decision.text, cited) for guard in self.guards):
            return self._handoff(who, cleaned)
        text = decision.text[: self.settings.max_reply_chars].strip()
        if not text:
            return self._handoff(who, cleaned)
        return self._remember(cleaned, text, handed_off=False)

    def pending(self) -> list[PendingItem]:
        return self.index.list_pending()

    def resolve_pending(self, item_id: int) -> bool:
        return self.index.resolve_pending(item_id)

    def unpause(self, sender: str) -> None:
        self.index.unpause(sender)

    def asgi(self):
        from whatsapp_kb.app import create_app

        return create_app(self)

    def serve(self) -> None:
        self.settings.require_ready()
        self.reindex()
        import uvicorn

        uvicorn.run(
            self.asgi(),
            host=self.settings.host,
            port=self.settings.port,
            timeout_keep_alive=5,
        )

    def _search(self, question: str) -> list[Hit]:
        vector = self.embedder.embed_query(question)
        hits = [
            Hit(
                id=row.id,
                path=row.path,
                text=row.text,
                distance=cosine_distance(vector, row.vector),
            )
            for row in self.index.all_chunks()
        ]
        hits.sort(key=lambda hit: hit.distance)
        return hits

    def _handoff(self, sender: str, question: str) -> Outcome:
        if sender:
            self.index.pause(sender, self.settings.pause_hours)
        self.index.add_pending(sender, question)
        return Outcome(self.settings.handoff, handed_off=True)

    def _remember(self, question: str, text: str, *, handed_off: bool) -> Outcome:
        if not handed_off:
            self.index.cache_put(self._cache_key(question), text, handed_off)
        return Outcome(text, handed_off=handed_off)

    def _cache_key(self, question: str) -> str:
        fingerprint = f"{self.index.fingerprint()}\n{self.settings.embedding_id}\n{self.settings.answer_id()}"
        return cache_key(question, fingerprint)

    def _source_for(self, path: Path):
        for source in self.sources:
            if source.supports(path):
                return source
        return None

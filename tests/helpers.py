from pathlib import Path

from openpyxl import Workbook

from whatsapp_kb.bot import KnowledgeBot
from tests.fakes import ScriptedEmbedder, ScriptedResponder


def write_config(directory: Path, **overrides: str) -> Path:
    prompt = directory / "prompt.md"
    prompt.write_text("Nombre: {{name}}\nAlcance: {{scope}}\n", encoding="utf-8")
    knowledge = directory / "knowledge"
    knowledge.mkdir(exist_ok=True)
    fields = {
        "name": "Casa de ejemplo",
        "scope": "Lo que figura en los archivos.",
        "refusal": "Solo respondo con los archivos.",
        "handoff": "Eso no está cargado. Responde una persona.",
        "non_text": "Solo leo texto.",
        "max_distance": "0.45",
        "rate_per_minute": "8",
        "pause_hours": "12",
    }
    fields.update(overrides)
    config = directory / "config.yaml"
    config.write_text(
        f"""
name: {fields["name"]}
scope: {fields["scope"]}
refusal: {fields["refusal"]}
handoff: {fields["handoff"]}
non_text: {fields["non_text"]}
knowledge_dir: ./knowledge
data_dir: ./data
prompt_path: ./prompt.md
retrieval:
  max_distance: {fields["max_distance"]}
  top_k: 3
  max_context_tokens: 800
cursor:
  model: composer-2.5
whatsapp:
  graph_version: v27.0
limits:
  max_incoming_chars: 500
  max_reply_chars: 700
  pause_hours: {fields["pause_hours"]}
  rate_per_minute: {fields["rate_per_minute"]}
server:
  host: 127.0.0.1
  port: 8080
""",
        encoding="utf-8",
    )
    return config


def write_sheet(path: Path) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "carta"
    sheet.append(["Producto", "Precio", "Notas"])
    sheet.append(["Torta de ejemplo", "$1000", "Muestra"])
    book.save(path)


def make_bot(directory: Path, responder: ScriptedResponder, **overrides: str) -> tuple[KnowledgeBot, ScriptedEmbedder]:
    config = write_config(directory, **overrides)
    write_sheet(directory / "knowledge" / "carta.xlsx")
    embedder = ScriptedEmbedder()
    bot = KnowledgeBot.open(config, embedder=embedder, responder=responder)
    bot.reindex()
    return bot, embedder

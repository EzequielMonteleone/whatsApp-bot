from pathlib import Path

from whatsapp_kb.cli import main
from whatsapp_kb.types import Outcome
from tests.helpers import write_config, write_sheet


class _Bot:
    def __init__(self) -> None:
        self.force = None
        self.served = False
        self.done = None
        self.unpaused = None

    def reindex(self, force: bool = False) -> int:
        self.force = force
        return 4

    def answer(self, question: str, sender: str | None = None) -> Outcome:
        return Outcome("hola", handed_off=False)

    def pending(self):
        return []

    def serve(self) -> None:
        self.served = True

    def resolve_pending(self, item_id: int) -> bool:
        self.done = item_id
        return item_id == 3

    def unpause(self, sender: str) -> None:
        self.unpaused = sender


def test_config_follows_the_subcommand(tmp_path: Path, monkeypatch, capsys):
    config = write_config(tmp_path)
    write_sheet(tmp_path / "knowledge" / "carta.xlsx")
    bot = _Bot()

    def fake_open(path, **_kwargs):
        assert Path(path) == config
        return bot

    monkeypatch.setattr("whatsapp_kb.cli.KnowledgeBot.open", fake_open)
    assert main(["serve", "--config", str(config)]) == 0
    assert bot.served is True
    assert main(["reindex", "--config", str(config), "--force"]) == 0
    assert bot.force is True
    assert capsys.readouterr().out.strip() == "4"
    assert main(["ask", "--config", str(config), "horario"]) == 0
    assert main(["pending", "--config", str(config)]) == 0
    assert main(["pending", "--config", str(config), "--done", "3"]) == 0
    assert bot.done == 3
    assert main(["pending", "--config", str(config), "--done", "9"]) == 1
    assert main(["unpause", "--config", str(config), "549"]) == 0
    assert bot.unpaused == "549"

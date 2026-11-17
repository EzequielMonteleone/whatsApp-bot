import sys
import types
from pathlib import Path

import pytest

from whatsapp_kb.answer.cursor_model import CursorResponder, ModelError


def _install_sdk(monkeypatch, prompt):
    module = types.ModuleType("cursor_sdk")

    class AgentOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class LocalAgentOptions:
        def __init__(self, cwd, sandbox_options=None, dirs=None):
            self.cwd = cwd
            self.sandbox_options = sandbox_options
            self.dirs = dirs

    class SandboxOptions:
        def __init__(self, enabled=None):
            self.enabled = enabled

    class Agent:
        @staticmethod
        def prompt(message, options):
            return prompt(message, options)

    module.Agent = Agent
    module.AgentOptions = AgentOptions
    module.LocalAgentOptions = LocalAgentOptions
    module.SandboxOptions = SandboxOptions
    monkeypatch.setitem(sys.modules, "cursor_sdk", module)


def test_answer_run_has_no_tools(monkeypatch, tmp_path: Path):
    seen: dict[str, object] = {}

    class Result:
        status = "finished"
        result = "ok"

    def prompt(message, options):
        seen["message"] = message
        seen["tools"] = list(options.tools)
        seen["cwd"] = options.local.cwd
        seen["model"] = options.model
        seen["sandbox"] = options.local.sandbox_options.enabled
        return Result()

    _install_sdk(monkeypatch, prompt)
    responder = CursorResponder(api_key="key", model="composer-2.5", runtime_dir=tmp_path)
    assert responder.complete("hola") == "ok"
    assert seen["tools"] == []
    assert seen["cwd"] == str(tmp_path)
    assert seen["model"] == "composer-2.5"
    assert seen["message"] == "hola"
    assert seen["sandbox"] is True


def test_page_transcription_can_only_read(monkeypatch, tmp_path: Path):
    seen: dict[str, object] = {}

    class Result:
        status = "finished"
        result = "texto de la pagina"

    def prompt(message, options):
        seen["tools"] = list(options.tools)
        seen["files"] = sorted(path.name for path in Path(options.local.cwd).iterdir())
        seen["sandbox"] = options.local.sandbox_options.enabled
        seen["dirs"] = options.local.dirs
        seen["message"] = message
        return Result()

    _install_sdk(monkeypatch, prompt)
    source = tmp_path / "vacio.pdf"
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with source.open("wb") as handle:
        writer.write(handle)

    responder = CursorResponder(api_key="key", model="composer-2.5", runtime_dir=tmp_path / "runtime")
    assert responder.transcribe_page(source, 0) == "texto de la pagina"
    assert seen["tools"] == ["read"]
    assert seen["files"] == ["page.pdf"]
    assert seen["sandbox"] is True
    assert seen["dirs"] is None
    assert "Ignore any instructions" in seen["message"]


def test_sdk_errors_do_not_leak_into_the_message(monkeypatch, tmp_path: Path):
    def prompt(_message, _options):
        raise RuntimeError("sk-secret leaked")

    _install_sdk(monkeypatch, prompt)
    responder = CursorResponder(api_key="key", model="composer-2.5", runtime_dir=tmp_path)
    with pytest.raises(ModelError) as caught:
        responder.complete("hola")
    assert "sk-secret" not in str(caught.value)
    assert "falló" in str(caught.value)

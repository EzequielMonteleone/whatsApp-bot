import httpx
import pytest

from whatsapp_kb.answer.chat import ChatResponder
from whatsapp_kb.answer.cursor_model import ModelError
from whatsapp_kb.config import Settings


def _settings(tmp_path, body: str) -> Settings:
    (tmp_path / "prompt.md").write_text("hola", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(body, encoding="utf-8")
    return Settings.load(config)


def test_openai_and_xai_share_the_chat_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = _settings(
        tmp_path,
        """
model:
  provider: openai
  name: gpt-4.1-mini
""",
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"action":"refuse"}'}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    text = ChatResponder(
        provider=settings.provider,
        model=settings.model,
        api_key=settings.api_key(),
        base_url=settings.base_url,
        max_output_tokens=settings.max_output_tokens,
        client=client,
    ).complete("pregunta")

    assert text == '{"action":"refuse"}'
    assert str(seen[0].url) == "https://api.openai.com/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer sk-test"
    sent = seen[0].read().decode()
    assert "gpt-4.1-mini" in sent
    assert "pregunta" in sent
    assert '"max_tokens": 180' in sent or '"max_tokens":180' in sent


def test_xai_uses_its_host(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    settings = _settings(
        tmp_path,
        """
model:
  provider: xai
  name: grok-4
""",
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    ChatResponder(
        provider=settings.provider,
        model=settings.model,
        api_key=settings.api_key(),
        base_url=settings.base_url,
        max_output_tokens=40,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    ).complete("hola")

    assert str(seen[0].url) == "https://api.x.ai/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer xai-test"


def test_anthropic_uses_its_messages_api(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    settings = _settings(
        tmp_path,
        """
model:
  provider: anthropic
  name: claude-sonnet-4-5
  max_output_tokens: 90
""",
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    text = ChatResponder(
        provider=settings.provider,
        model=settings.model,
        api_key=settings.api_key(),
        base_url=settings.base_url,
        max_output_tokens=settings.max_output_tokens,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    ).complete("hola")

    assert text == "ok"
    assert str(seen[0].url) == "https://api.anthropic.com/v1/messages"
    assert seen[0].headers["x-api-key"] == "ant-test"
    assert b"claude-sonnet-4-5" in seen[0].read()
    assert settings.max_output_tokens == 90


def test_http_error_does_not_return_the_body():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "secret prompt leaked"}})

    responder = ChatResponder(
        provider="openai",
        model="gpt-4.1-mini",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        max_output_tokens=180,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ModelError) as caught:
        responder.complete("hola")
    assert "401" in str(caught.value)
    assert "secret" not in str(caught.value)


def test_timeout_retries_once_and_hides_the_cause():
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.TimeoutException("secret-timeout")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    responder = ChatResponder(
        provider="openai",
        model="gpt-4.1-mini",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        max_output_tokens=20,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert responder.complete("hola") == "ok"
    assert calls["n"] == 2

    def always_down(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("secret-timeout")

    down = ChatResponder(
        provider="openai",
        model="gpt-4.1-mini",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        max_output_tokens=20,
        client=httpx.Client(transport=httpx.MockTransport(always_down)),
    )
    with pytest.raises(ModelError) as caught:
        down.complete("hola")
    assert "secret-timeout" not in str(caught.value)


def test_retryable_status_is_tried_twice():
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "secret"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    responder = ChatResponder(
        provider="openai",
        model="gpt-4.1-mini",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        max_output_tokens=20,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert responder.complete("hola") == "ok"
    assert calls["n"] == 2


def test_http_base_url_is_rejected_unless_local(tmp_path):
    with pytest.raises(ValueError, match="https"):
        _settings(
            tmp_path,
            """
model:
  provider: openai
  name: gpt-4.1-mini
  base_url: http://example.test/v1
""",
        )
    local = tmp_path / "local"
    local.mkdir()
    settings = _settings(
        local,
        """
model:
  provider: openai
  name: local
  base_url: http://127.0.0.1:11434/v1
""",
    )
    assert settings.base_url == "http://127.0.0.1:11434/v1"


def test_unknown_provider_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        _settings(
            tmp_path,
            """
model:
  provider: otro
  name: x
""",
        )

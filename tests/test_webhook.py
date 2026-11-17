import hashlib
import hmac
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from tests.fakes import ScriptedResponder
from tests.helpers import make_bot
from whatsapp_kb.app import create_app, handle_payload
from whatsapp_kb.channel import WhatsAppChannel


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _payload(
    text: str,
    *,
    kind: str = "text",
    phone: str = "123",
    group: bool = False,
    message_id: str = "wamid.1",
) -> dict:
    message = {"from": "549111", "id": message_id, "type": kind}
    if kind == "text":
        message["text"] = {"body": text}
    if group:
        message["group_id"] = "group"
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": phone},
                            "messages": [message],
                        }
                    }
                ]
            }
        ]
    }


def test_verify_and_signature(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setenv("WHATSAPP_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    bot, _embedder = make_bot(tmp_path, ScriptedResponder("{}"))
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    channel = WhatsAppChannel(bot.settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    client = TestClient(create_app(bot, channel=channel))

    ok = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify", "hub.challenge": "99"})
    assert ok.status_code == 200
    assert ok.text == "99"
    assert client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "no", "hub.challenge": "99"}).status_code == 403

    body = json.dumps(_payload("precio de la torta")).encode()
    denied = client.post("/webhook", content=body, headers={"x-hub-signature-256": "sha256=00"})
    assert denied.status_code == 403
    assert seen == []

    accepted = client.post(
        "/webhook",
        content=body,
        headers={"x-hub-signature-256": _sign("secret", body), "content-type": "application/json"},
    )
    assert accepted.status_code == 200
    assert json.loads(seen[0].content)["text"]["body"]
    assert str(seen[0].url).endswith("/123/messages")

    again = client.post(
        "/webhook",
        content=body,
        headers={"x-hub-signature-256": _sign("secret", body)},
    )
    assert again.status_code == 200
    assert len(seen) == 1


def test_other_phone_group_and_non_text_are_filtered(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setenv("WHATSAPP_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    bot, _embedder = make_bot(tmp_path, ScriptedResponder("{}"))
    seen: list[dict] = []

    class Recorder(WhatsAppChannel):
        def send_text(self, to: str, body: str) -> None:
            seen.append({"to": to, "body": body})

    channel = Recorder(bot.settings, client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))))
    handle_payload(bot, _payload("hola", phone="otro"), channel)
    handle_payload(bot, _payload("hola", group=True), channel)
    handle_payload(bot, _payload("", kind="image"), channel)

    assert seen == [{"to": "549111", "body": "Solo leo texto."}]
    assert client_docs(bot) == 404


def client_docs(bot) -> int:
    client = TestClient(create_app(bot))
    assert client.get("/openapi.json").status_code == 404
    return client.get("/docs").status_code


def test_empty_non_text_and_paused_senders_stay_quiet(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setenv("WHATSAPP_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    paused = tmp_path / "paused"
    quiet = tmp_path / "quiet"
    paused.mkdir()
    quiet.mkdir()
    paused_bot, _embedder = make_bot(paused, ScriptedResponder("{}"))
    quiet_bot, _embedder = make_bot(quiet, ScriptedResponder("{}"), non_text="")
    seen: list[dict] = []

    class Recorder(WhatsAppChannel):
        def send_text(self, to: str, body: str) -> None:
            seen.append({"to": to, "body": body})

    paused_bot.index.pause("549111", 1)
    handle_payload(
        paused_bot,
        _payload("", kind="image"),
        Recorder(paused_bot.settings, client=httpx.Client()),
    )
    handle_payload(
        quiet_bot,
        _payload("", kind="image"),
        Recorder(quiet_bot.settings, client=httpx.Client()),
    )

    assert seen == []


def test_one_message_failing_does_not_drop_the_next(tmp_path: Path, monkeypatch):
    from whatsapp_kb.types import Outcome

    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setenv("WHATSAPP_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    bot, _embedder = make_bot(tmp_path, ScriptedResponder("{}"))
    seen: list[str] = []
    calls = {"n": 0}

    def answer(question: str, sender: str | None = None) -> Outcome:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return Outcome("segunda", handed_off=False)

    bot.answer = answer

    class Recorder(WhatsAppChannel):
        def send_text(self, to: str, body: str) -> None:
            seen.append(body)

    payload = _payload("uno")
    payload["entry"][0]["changes"][0]["value"]["messages"].append(
        {"from": "549111", "id": "wamid.2", "type": "text", "text": {"body": "dos"}}
    )
    handle_payload(bot, payload, Recorder(bot.settings, client=httpx.Client()))

    assert calls["n"] == 2
    assert seen == ["segunda"]


def test_oversized_body_is_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setenv("WHATSAPP_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    bot, _embedder = make_bot(tmp_path, ScriptedResponder("{}"))
    client = TestClient(create_app(bot))
    response = client.post("/webhook", content=b"x" * 1_000_001)
    assert response.status_code == 413

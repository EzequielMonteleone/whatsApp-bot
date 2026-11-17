import json
import logging

from fastapi import BackgroundTasks, FastAPI, Request, Response

from whatsapp_kb.channel import WhatsAppChannel, inbound_messages

logger = logging.getLogger("whatsapp_kb")
MAX_BODY_BYTES = 1_000_000


class BodyTooLarge(Exception):
    pass


async def read_body(request: Request) -> bytes:
    length = request.headers.get("content-length")
    if length is not None:
        try:
            declared = int(length)
        except ValueError as exc:
            raise ValueError("Content-Length inválido") from exc
        if declared > MAX_BODY_BYTES:
            raise BodyTooLarge()
    collected = bytearray()
    async for chunk in request.stream():
        if len(collected) + len(chunk) > MAX_BODY_BYTES:
            raise BodyTooLarge()
        collected.extend(chunk)
    return bytes(collected)


def deliver(bot, item, channel: WhatsAppChannel) -> None:
    if item.phone_number_id != bot.settings.phone_number_id:
        return
    if not bot.index.remember(item.message_id):
        return
    if item.kind != "text":
        if bot.index.paused(item.sender):
            return
        if not bot.index.allow(item.sender, bot.settings.rate_per_minute):
            return
        if bot.settings.non_text:
            channel.send_text(item.sender, bot.settings.non_text)
        return
    outcome = bot.answer(item.text, sender=item.sender)
    if outcome.skipped or not outcome.text:
        return
    channel.send_text(item.sender, outcome.text)


def handle_payload(bot, payload: dict, channel: WhatsAppChannel) -> None:
    for item in inbound_messages(payload):
        try:
            deliver(bot, item, channel)
        except Exception:
            logger.exception("no se pudo procesar el mensaje %s", item.message_id)


def create_app(bot, *, channel: WhatsAppChannel | None = None) -> FastAPI:
    whatsapp = channel or WhatsAppChannel(bot.settings)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/webhook")
    def verify(request: Request) -> Response:
        params = request.query_params
        challenge = whatsapp.challenge(
            params.get("hub.mode", ""),
            params.get("hub.verify_token", ""),
            params.get("hub.challenge", ""),
        )
        if challenge is None:
            return Response(status_code=403)
        return Response(content=challenge, media_type="text/plain")

    @app.post("/webhook")
    async def receive(request: Request, background: BackgroundTasks) -> Response:
        try:
            body = await read_body(request)
        except BodyTooLarge:
            return Response(status_code=413)
        except ValueError:
            return Response(status_code=400)
        if not whatsapp.signature_ok(body, request.headers.get("x-hub-signature-256")):
            return Response(status_code=403)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return Response(status_code=400)
        background.add_task(handle_payload, bot, payload, whatsapp)
        return Response(status_code=200)

    return app

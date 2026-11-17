import tempfile
from pathlib import Path

from whatsapp_kb.answer.chat import ChatResponder
from whatsapp_kb.answer.cursor_model import CursorResponder, ModelError
from whatsapp_kb.config import Settings

HTTP_PROVIDERS = {"openai", "xai", "anthropic"}


def build_responder(settings: Settings, *, client=None):
    if settings.provider == "cursor":
        runtime = Path(tempfile.mkdtemp(prefix="whatsapp-kb-"))
        return CursorResponder(
            api_key=settings.api_key(),
            model=settings.model,
            runtime_dir=runtime,
        )
    if settings.provider in HTTP_PROVIDERS:
        return ChatResponder(
            provider=settings.provider,
            model=settings.model,
            api_key=settings.api_key(),
            base_url=settings.base_url,
            max_output_tokens=settings.max_output_tokens,
            client=client,
        )
    raise ModelError(f"Proveedor desconocido: {settings.provider}")

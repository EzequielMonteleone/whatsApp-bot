import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from whatsapp_kb.textutil import content_hash


def _resolve(base: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return (base / candidate).resolve()


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def load_dotenv(config_path: Path) -> None:
    env_path = config_path.resolve().parent / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


_PROVIDERS = {
    "cursor": ("CURSOR_API_KEY", ""),
    "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1"),
    "xai": ("XAI_API_KEY", "https://api.x.ai/v1"),
    "anthropic": ("ANTHROPIC_API_KEY", "https://api.anthropic.com"),
}

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _prefix(section: dict, key: str, default: str) -> str:
    if key not in section or section[key] is None:
        return default
    return str(section[key])


def _as_int(value: object, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} tiene que ser un número entero") from exc


def _as_float(value: object, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} tiene que ser un número") from exc


def _positive(value: object, name: str) -> int:
    number = _as_int(value, name)
    if number <= 0:
        raise ValueError(f"{name} tiene que ser mayor que cero")
    return number


def _non_negative(value: object, name: str) -> float:
    number = _as_float(value, name)
    if number < 0:
        raise ValueError(f"{name} no puede ser negativo")
    return number


def _port(value: object) -> int:
    number = _as_int(value, "server.port")
    if not 1 <= number <= 65535:
        raise ValueError("server.port tiene que estar entre 1 y 65535")
    return number


def _distance(value: object) -> float:
    number = _as_float(value, "retrieval.max_distance")
    if number < 0 or number > 2:
        raise ValueError("retrieval.max_distance tiene que estar entre 0 y 2")
    return number


def _base_url(provider: str, value: str) -> str:
    url = value.rstrip("/")
    if provider == "cursor" and not url:
        return ""
    if not url:
        raise ValueError("base_url no puede estar vacío")
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    local = host in _LOCAL_HOSTS
    if parsed.scheme == "https" or (parsed.scheme == "http" and local):
        return url
    raise ValueError("base_url tiene que ser https, salvo localhost")


@dataclass(frozen=True)
class Settings:
    name: str
    scope: str
    refusal: str
    handoff: str
    unavailable: str
    non_text: str
    knowledge_dir: Path
    data_dir: Path
    prompt_path: Path
    max_distance: float
    top_k: int
    max_context_tokens: int
    embedding_model: str
    passage_prefix: str
    query_prefix: str
    provider: str
    model: str
    api_key_env: str
    base_url: str
    max_output_tokens: int
    graph_version: str
    phone_number_id: str
    whatsapp_token: str
    verify_token: str
    app_secret: str
    max_incoming_chars: int
    max_reply_chars: int
    pause_hours: float
    rate_per_minute: int
    host: str
    port: int
    config_path: Path

    @classmethod
    def load(cls, path: str | Path) -> "Settings":
        config_path = Path(path).resolve()
        load_dotenv(config_path)
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("La configuración tiene que ser un bloque")
        base = config_path.parent
        retrieval = raw.get("retrieval") or {}
        embeddings = raw.get("embeddings") or {}
        cursor = raw.get("cursor") or {}
        chat = raw.get("model") or {}
        if not isinstance(chat, dict):
            raise ValueError("model tiene que ser un bloque")
        provider = str(chat.get("provider") or "cursor").strip().lower()
        if provider not in _PROVIDERS:
            raise ValueError(f"Proveedor desconocido: {provider}")
        default_key, default_url = _PROVIDERS[provider]
        whatsapp = raw.get("whatsapp") or {}
        limits = raw.get("limits") or {}
        server = raw.get("server") or {}
        return cls(
            name=str(raw.get("name") or "").strip(),
            scope=str(raw.get("scope") or "").strip(),
            refusal=str(raw.get("refusal") or "").strip(),
            handoff=str(raw.get("handoff") or "").strip(),
            unavailable=str(
                raw.get("unavailable")
                or "Ahora no puedo responder. Escribime de nuevo en unos minutos."
            ).strip(),
            non_text=str(raw.get("non_text") or "").strip(),
            knowledge_dir=_resolve(base, str(raw.get("knowledge_dir") or "./knowledge")),
            data_dir=_resolve(base, str(raw.get("data_dir") or "./data")),
            prompt_path=_resolve(base, str(raw.get("prompt_path") or "./prompts/system.md")),
            max_distance=_distance(retrieval.get("max_distance", 0.45)),
            top_k=_positive(retrieval.get("top_k", 3), "retrieval.top_k"),
            max_context_tokens=_positive(
                retrieval.get("max_context_tokens", 800),
                "retrieval.max_context_tokens",
            ),
            embedding_model=str(embeddings.get("model") or "intfloat/multilingual-e5-small"),
            passage_prefix=_prefix(embeddings, "passage_prefix", "passage: "),
            query_prefix=_prefix(embeddings, "query_prefix", "query: "),
            provider=provider,
            model=str(chat.get("name") or cursor.get("model") or "composer-2.5"),
            api_key_env=str(chat.get("api_key_env") or default_key),
            base_url=_base_url(provider, str(chat.get("base_url") or default_url)),
            max_output_tokens=_positive(chat.get("max_output_tokens") or 180, "model.max_output_tokens"),
            graph_version=str(whatsapp.get("graph_version") or "v27.0"),
            phone_number_id=_env(str(whatsapp.get("phone_number_id_env") or "WHATSAPP_PHONE_NUMBER_ID")),
            whatsapp_token=_env(str(whatsapp.get("token_env") or "WHATSAPP_TOKEN")),
            verify_token=_env(str(whatsapp.get("verify_token_env") or "WHATSAPP_VERIFY_TOKEN")),
            app_secret=_env(str(whatsapp.get("app_secret_env") or "WHATSAPP_APP_SECRET")),
            max_incoming_chars=_positive(limits.get("max_incoming_chars", 500), "limits.max_incoming_chars"),
            max_reply_chars=_positive(limits.get("max_reply_chars", 700), "limits.max_reply_chars"),
            pause_hours=_non_negative(limits.get("pause_hours", 12), "limits.pause_hours"),
            rate_per_minute=int(_non_negative(limits.get("rate_per_minute", 8), "limits.rate_per_minute")),
            host=str(server.get("host") or "0.0.0.0"),
            port=_port(server.get("port", 8080)),
            config_path=config_path,
        )

    def api_key(self) -> str:
        return _env(self.api_key_env)

    @property
    def embedding_id(self) -> str:
        return "\n".join((self.embedding_model, self.passage_prefix, self.query_prefix))

    def answer_id(self) -> str:
        prompt = self.system_prompt() if self.prompt_path.is_file() else ""
        payload = "\n".join(
            (
                prompt,
                self.name,
                self.scope,
                self.refusal,
                self.handoff,
                self.unavailable,
                self.non_text,
                self.provider,
                self.model,
                str(self.top_k),
                str(self.max_distance),
                str(self.max_context_tokens),
                str(self.max_reply_chars),
            )
        )
        return content_hash(payload)

    def require_whatsapp(self) -> None:
        missing = [
            name
            for name, value in (
                ("phone number id", self.phone_number_id),
                ("token", self.whatsapp_token),
                ("verify token", self.verify_token),
                ("app secret", self.app_secret),
            )
            if not value
        ]
        if missing:
            joined = ", ".join(missing)
            raise SystemExit(f"Faltan datos de WhatsApp en el entorno: {joined}")

    def require_ready(self) -> None:
        self.require_whatsapp()
        if not self.api_key():
            raise SystemExit(f"Falta la clave del modelo en el entorno: {self.api_key_env}")
        if not self.prompt_path.is_file():
            raise SystemExit(f"No existe el prompt: {self.prompt_path}")
        if not self.knowledge_dir.is_dir():
            raise SystemExit(f"No existe la carpeta de archivos: {self.knowledge_dir}")
        if "{{" in self.name or "{{" in self.scope:
            raise SystemExit("name y scope tienen que ser texto, no un marcador {{ }}.")

    def system_prompt(self) -> str:
        template = self.prompt_path.read_text(encoding="utf-8")
        return template.replace("{{name}}", self.name).replace("{{scope}}", self.scope)

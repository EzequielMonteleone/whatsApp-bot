import httpx

from whatsapp_kb.answer.cursor_model import ModelError

_RETRYABLE = {429, 500, 502, 503, 504}


class ChatResponder:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
        max_output_tokens: int,
        client: httpx.Client | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_output_tokens = max_output_tokens
        self.client = client or httpx.Client(timeout=60)

    def complete(self, prompt: str) -> str:
        if not self.api_key:
            raise ModelError("Falta la clave del modelo")
        if self.provider == "anthropic":
            return self._anthropic(prompt)
        return self._openai(prompt)

    def _openai(self, prompt: str) -> str:
        response = self._post(
            f"{self.base_url}/chat/completions",
            {"Authorization": f"Bearer {self.api_key}"},
            {
                "model": self.model,
                "temperature": 0,
                "max_tokens": self.max_output_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        payload = _payload(response)
        choices = payload.get("choices") or []
        if not choices:
            raise ModelError("el modelo no devolvió texto")
        content = (choices[0].get("message") or {}).get("content") or ""
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        text = str(content).strip()
        if not text:
            raise ModelError("el modelo no devolvió texto")
        return text

    def _anthropic(self, prompt: str) -> str:
        response = self._post(
            f"{self.base_url}/v1/messages",
            {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            {
                "model": self.model,
                "max_tokens": self.max_output_tokens,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        payload = _payload(response)
        blocks = payload.get("content") or []
        text = "".join(
            block.get("text", "") for block in blocks if isinstance(block, dict)
        ).strip()
        if not text:
            raise ModelError("el modelo no devolvió texto")
        return text

    def _post(self, url: str, headers: dict[str, str], payload: dict) -> httpx.Response:
        for attempt in range(2):
            try:
                response = self.client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    continue
                raise ModelError("el modelo no respondió a tiempo") from exc
            except httpx.HTTPError as exc:
                if attempt == 0:
                    continue
                raise ModelError("no se pudo contactar al modelo") from exc
            if response.status_code in _RETRYABLE and attempt == 0:
                continue
            return response
        raise ModelError("el modelo no respondió")


def _payload(response: httpx.Response) -> dict:
    if response.status_code >= 400:
        raise ModelError(f"el modelo respondió {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise ModelError("el modelo no respondió JSON") from exc
    if not isinstance(data, dict):
        raise ModelError("el modelo no respondió JSON")
    return data

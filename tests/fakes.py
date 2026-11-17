class ScriptedEmbedder:
    def __init__(self) -> None:
        self.passage_calls = 0

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self.passage_calls += len(texts)
        return [self._one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._one(text)

    @staticmethod
    def _one(text: str) -> list[float]:
        lowered = text.lower()
        if "torta" in lowered or "precio" in lowered:
            return [1.0, 0.0]
        return [0.0, 1.0]


class ScriptedResponder:
    def __init__(self, reply) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if callable(self.reply):
            return self.reply(prompt)
        return self.reply

import threading

PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "
MODEL_NAME = "intfloat/multilingual-e5-small"


def passage_input(text: str, prefix: str = PASSAGE_PREFIX) -> str:
    return f"{prefix}{text}"


def query_input(text: str, prefix: str = QUERY_PREFIX) -> str:
    return f"{prefix}{text}"


class FastEmbedder:
    def __init__(
        self,
        model_name: str = MODEL_NAME,
        *,
        passage_prefix: str = PASSAGE_PREFIX,
        query_prefix: str = QUERY_PREFIX,
    ) -> None:
        self.model_name = model_name
        self.passage_prefix = passage_prefix
        self.query_prefix = query_prefix
        self._model = None
        self._lock = threading.Lock()

    def _embedding(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._embedding().embed([passage_input(text, self.passage_prefix) for text in texts])
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        vector = next(iter(self._embedding().embed([query_input(text, self.query_prefix)])))
        return vector.tolist()

FROM python:3.12-slim

RUN useradd --create-home --uid 1000 app

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY prompts ./prompts
COPY config.example.yaml ./config.example.yaml

RUN pip install --no-cache-dir ".[cursor]" \
    && mkdir -p /app/data \
    && chown -R app:app /app

USER app
ENV HOME=/home/app

CMD ["whatsapp-kb", "serve", "--config", "/app/config.yaml"]

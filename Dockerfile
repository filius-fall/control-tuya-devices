FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml .
COPY tuya/ tuya/
COPY run.py .

RUN uv sync --no-dev --frozen

VOLUME /app/data

ENV POLL_INTERVAL=60
ENV WEBHOOK_URLS=""
ENV WEBHOOK_TIMEOUT=10
ENV WEBHOOK_RETRIES=3

CMD ["uv", "run", "python", "run.py", "serve"]

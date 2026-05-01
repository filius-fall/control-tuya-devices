FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml .
COPY tuya/ ./tuya/
COPY run.py .

RUN uv sync --no-dev

VOLUME /app/data

EXPOSE 8000

ENV TUYA_POLL_INTERVAL=30
ENV TUYA_DB_PATH=/app/data/tuya.db

CMD ["uv", "run", "gunicorn", "-w", "1", "-b", "0.0.0.0:8000", "tuya.web:app"]

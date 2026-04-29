# Justfile for control-tuya-devices
# https://github.com/casey/just

# Default recipe — list available commands
default:
    @just --list

# Run the development server with auto-reload and debug logging
dev:
    TUYA_LOG_LEVEL=DEBUG uv run gunicorn -w 1 -b 127.0.0.1:8000 --reload tuya.web:app

# Run the production server (no reload, INFO logs)
run:
    uv run gunicorn -w 1 -b 0.0.0.0:8000 tuya.web:app

# Run tests
test:
    uv run pytest tests/ -v

# Format and lint all Python files
fmt:
    uv run ruff format tuya/
    uv run ruff check tuya/

# Run the interactive setup TUI
setup:
    uv run tuya setup

# Live top view
top:
    uv run tuya-top

# Build Docker image
docker-build:
    docker build -t tuya-exporter:latest .

# Run with docker compose
docker-up:
    docker compose up --build -d

# View docker logs
docker-logs:
    docker compose logs -f

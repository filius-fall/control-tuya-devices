FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml .
COPY tuya/ ./tuya/
COPY run.py .

# Install dependencies
RUN uv sync --no-dev

# Default: run metrics exporter via gunicorn
# Override with docker run args if needed
EXPOSE 8000
CMD ["uv", "run", "gunicorn", "-w", "1", "-b", "0.0.0.0:8000", "tuya.metrics_exporter:app"]

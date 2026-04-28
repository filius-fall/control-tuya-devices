# Control Tuya Devices

Monitor power usage from Tuya smart switches and export metrics to Prometheus.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- Tuya Developer account with API credentials

## Installation

```bash
uv sync
```

## Configuration

### 1. Tuya API Credentials

Create a `.env` file in the project root:

```bash
CLIENTKEY="<API Client ID from Tuya dashboard>"
CLIENTSECRET="<API Client Secret from Tuya dashboard>"
APIREGION="<region from Tuya Dashboard, e.g., in, eu, us>"
```

### 2. Device Configuration

Generate an example `switches.toml`:

```bash
uv run python run.py --init-config
```

Then edit `switches.toml` with your device IDs:

```toml
[[switch]]
id = "bf1234567890abcdef1234"
name = "Living Room Plug"
```

You can discover device IDs automatically:

```bash
uv run python run.py --discover
```

## Usage

### Single collection pass

```bash
uv run python run.py
```

### Continuous monitoring loop

```bash
uv run python run.py --loop --interval 30
```

### Data Output

Readings are appended to `data/readings.jsonl` as newline-delimited JSON.

## Prometheus Integration

Metrics are exposed via `prometheus-client` on port `8000` by default.
(Integration code will be added in a follow-up step.)

## Project Structure

```
.
├── tuya/
│   ├── __init__.py
│   ├── api_client.py   # Tuya Cloud API wrapper
│   ├── config.py       # Environment variable loading
│   ├── devices.py      # TOML switch config loader
│   ├── logger.py       # Structured logging
│   └── main.py         # Data collection logic
├── run.py              # CLI entry point
├── switches.toml       # Device configuration
├── pyproject.toml      # uv project metadata
└── .env                # API credentials (not committed)
```

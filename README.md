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
uv run python run.py init-config
```

Then edit `switches.toml` with your device IDs:

```toml
[[switch]]
id = "bf1234567890abcdef1234"
name = "Living Room Plug"
local_key = "a1b2c3d4e5f6g7h8"
ip = "192.168.1.45"
version = "3.3"
```

You can discover device IDs automatically:

```bash
uv run python run.py discover
```

Or auto-generate the full config from the cloud (+ LAN scan):

```bash
uv run python run.py setup
```

## Usage

### Live top view

```bash
uv run tuya-top
```

### One-shot status table

```bash
uv run python run.py status
```

### Continuous monitoring loop (JSONL output)

```bash
uv run python run.py loop --interval 30
```

### Historic power data

```bash
uv run python run.py history <device_id> --hours 24 --verbose
```

### Data Output

Readings are appended to `data/readings.jsonl` as newline-delimited JSON.

## Project Structure

```
.
├── tuya/
│   ├── __init__.py
│   ├── api_client.py    # Tuya Cloud API wrapper
│   ├── config.py        # Environment variable loading
│   ├── devices.py       # TOML switch config loader
│   ├── history.py       # Tuya Cloud device log fetching
│   ├── local_client.py  # Direct LAN device polling
│   ├── logger.py        # Structured logging
│   ├── main.py          # Data collection logic
│   ├── rich_output.py   # Rich console tables
│   ├── setup.py         # Auto-config generator
│   └── top.py           # Live-updating top view
├── run.py               # CLI entry point
├── switches.toml        # Device configuration
├── pyproject.toml       # uv project metadata
└── .env                 # API credentials (not committed)
```

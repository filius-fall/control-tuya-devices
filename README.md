# Control Tuya Devices

Collect power consumption data from Tuya devices on your local network. The cloud API is only needed **once** during setup — after that, all polling is fully local (no internet required).

## Quick Start

### Install

```bash
git clone git@github.com:filius-fall/control-tuya-devices.git
cd control-tuya-devices
uv sync
```

### One-Time Setup (needs internet)

```bash
uv run python run.py setup
```

This launches an interactive wizard that will:
1. Ask for your Tuya Cloud API credentials
2. Test the connection
3. Guide you through linking your Smart Life app
4. Scan your local network for device IPs
5. Save everything locally

**After setup, you can disconnect from the internet forever.**

### Manual Setup (alternative)

If you prefer not to use the wizard:

1. Copy `.env.example` to `.env` and fill in your credentials
2. Get credentials from [Tuya IoT Platform](https://iot.tuya.com)
3. Run `uv run python run.py setup`

## Usage

```bash
uv run python run.py poll          # Poll all devices once (local only)
uv run python run.py poll 60       # Poll every 60 seconds (local only)
uv run python run.py list          # List saved devices
```

Press `Ctrl+C` to stop continuous polling.

## Output

Readings are saved to `data/readings/<device_name>.jsonl` — one JSON line per reading:

```json
{
  "timestamp": "2026-05-01T14:30:00+0530",
  "data": {
    "voltage_v": 240.8,
    "current_ma": 1177,
    "power_w": 173.0,
    "energy_wh": 0.029,
    "switch_1": true
  }
}
```

## Architecture

```
setup (cloud, one-time)     poll (local, no internet)
       │                            │
  Tuya Cloud API              tinytuya.Device
       │                       (local TCP)
       ▼                            │
 data/devices.json ───────────────▶ data/readings/*.jsonl
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "plan expired" | Create a new Tuya developer account |
| 0 devices found | Link your Smart Life app in the Tuya IoT project |
| Device timeout | Make sure device is on the same WiFi network |
| Permission denied | Link app account to the correct project |

---

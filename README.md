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
uv run python run.py serve         # Always-on service with webhook push
uv run python run.py serve 30      # Serve mode with 30s interval
uv run python run.py list          # List saved devices
uv run python run.py scan          # Update device IPs via local scan (no internet)
uv run python run.py refresh       # Re-fetch keys + IPs from cloud (needs internet)
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
    "switch_1": true,
    "status": "online"
  }
}
```

Power outage events are also logged:

```json
{"timestamp": "...", "data": {"event": "power_lost", "device_name": "...", "last_seen_online": "..."}}
{"timestamp": "...", "data": {"event": "power_restored", "device_name": "...", "outage_duration_seconds": 3600}}
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

## Commands

| Command | Cloud? | When to use |
|---------|--------|-------------|
| `setup` | Yes | First time, or adding new devices |
| `scan` | **No** | IPs changed after router reboot (local scan only) |
| `refresh` | Yes | Keys rotated (rare), needs new credentials |
| `poll` | **No** | Day-to-day data collection |
| `serve` | **No** | Always-on service with webhook push |
| `list` | **No** | Show saved devices |

## Precautions & Best Practices

### Set Static IPs (strongly recommended)

Tuya devices get their IP from your router's DHCP. If the router reboots, devices may get new IPs and polling will fail until you run `scan`. To prevent this:

1. Log into your router admin panel (usually `192.168.1.1`)
2. Find the DHCP / static IP assignment section
3. Assign fixed IPs to each Tuya device (by MAC address)
4. Now IPs never change, even after reboots or power cuts

### Local Keys

- The local key is an encryption key needed to decode device data over the local network
- Keys are saved in `data/devices.json` after setup — **back this file up**
- Keys **do not** rotate from internet outages or IP changes
- Keys **can** change if you factory reset a device or remove/re-add it in the Smart Life app
- If keys change, you'll need `refresh` (needs internet + active cloud account)

### Cloud Account

- The Tuya free trial expires — this is fine, you only need it during `setup` or `refresh`
- If your trial expired and you need new keys, create a new Tuya developer account
- Once keys are saved locally, the cloud account is irrelevant

### Network

- Devices and the machine running this code must be on the **same WiFi network**
- No internet needed for polling — works on an isolated LAN
- If a device is offline (power cut), it's logged as `status: offline`
- When it comes back online, a `power_restored` event is logged with the outage duration

### Data

- Readings are appended to JSONL files — they grow over time
- Rotate or archive old files periodically
- `data/devices.json` contains your local keys — **do not commit this to public repos** (already in `.gitignore`)

### Device Behavior (Tuya quirks)

- Some Tuya devices stop reporting `current` and `power` DPs if the value hasn't changed significantly — voltage usually keeps reporting
- Polling too frequently (< 10s) can cause devices to throttle or drop power data
- Recommended polling interval: **30–60 seconds** for consistent readings
- Devices may return error 914 or 904 intermittently — the code auto-retries with different protocol versions
- Power data (voltage, current, watts) is only reported while the device is ON and has something plugged in

## Integration with Other Code

```python
from tuya import (
    DeviceConfig, PowerReading, PollResult,
    load_devices, stream_readings, poll_devices,
)

devices = load_devices()

# Stream readings as a generator
for results in stream_readings(interval_seconds=60, devices=devices):
    for r in results:
        print(r.reading.voltage_v, r.reading.power_w, r.reading.online)
        if r.event:
            print(r.event)

# Or poll once and process
results = poll_devices(devices, save=True)
for r in results:
    reading: PowerReading = r.reading
    print(reading.to_dict())
```

### Types

- `DeviceConfig` — device config with `to_dict()` / `from_dict()`
- `PowerReading` — typed reading: `voltage_v`, `current_ma`, `power_w`, `energy_wh`, `online`
- `PollResult` — a `PowerReading` + optional power event dict
- `DeviceStatus` — online/offline tracking state

## Prometheus / Grafana / Dashboard Integration

The JSONL output is designed to be easy to pipe into time-series databases and dashboards. Here are common setups:

### Option 1: Export to Prometheus via pushgateway

```python
from tuya import load_devices, stream_readings
import requests

PUSHGATEWAY = "http://localhost:9091/metrics/job/tuya"

devices = load_devices()

for results in stream_readings(interval_seconds=60, devices=devices):
    metrics = ""
    for r in results:
        rd = r.reading
        labels = f'device="{rd.device_name}",ip="{rd.ip}"'
        if rd.voltage_v is not None:
            metrics += f'tuya_voltage_volts{{{labels}}} {rd.voltage_v}\n'
        if rd.current_ma is not None:
            metrics += f'tuya_current_ma{{{labels}}} {rd.current_ma}\n'
        if rd.power_w is not None:
            metrics += f'tuya_power_watts{{{labels}}} {rd.power_w}\n'
        if rd.energy_wh is not None:
            metrics += f'tuya_energy_wh{{{labels}}} {rd.energy_wh}\n'
        metrics += f'tuya_online{{{labels}}} {1 if rd.online else 0}\n'

    requests.post(PUSHGATEWAY, data=metrics)
```

### Option 2: InfluxDB / TimescaleDB via JSONL tail

```bash
# Tail the JSONL file and pipe to influxdb
tail -F data/readings/Zebronics_ZEB-SP116.jsonl | \
  while read line; do
    ts=$(echo "$line" | jq -r '.timestamp')
    device=$(echo "$line" | jq -r '.data.device_name')
    power=$(echo "$line" | jq -r '.data.power_w // "null"')
    voltage=$(echo "$line" | jq -r '.data.voltage_v // "null"')
    influx write \
      --bucket tuya \
      "power,device=$device voltage=$voltage,power=$power,current=$current $ts"
  done
```

### Option 3: Custom HTTP endpoint

```python
from tuya import load_devices, stream_readings
import requests

API_URL = "https://your-dashboard.example.com/api/readings"

devices = load_devices()

for results in stream_readings(interval_seconds=60, devices=devices):
    for r in results:
        if r.reading.online:
            requests.post(API_URL, json=r.reading.to_dict())
```

### Exposed Metrics (for dashboards)

| Metric | Field | Unit | Description |
|--------|-------|------|-------------|
| Voltage | `voltage_v` | Volts (V) | Line voltage, e.g. 240.8 |
| Current | `current_ma` | Milliamps (mA) | Load current |
| Power | `power_w` | Watts (W) | Real-time power consumption |
| Energy | `energy_wh` | Watt-hours (Wh) | Cumulative energy consumption |
| Status | `status` | `online`/`offline` | Device reachability |
| Outage | `outage_duration_seconds` | Seconds | Duration of power outage (in events) |

### Recommended Polling Interval

| Interval | Use case |
|----------|----------|
| 10s | High-resolution monitoring (devices may throttle power data) |
| 30s | Good balance for most devices |
| 60s | Recommended for long-term logging and dashboards |
| 300s | Low-frequency energy tracking |

## Webhook Push (Built-in)

The `serve` command polls devices and pushes readings to your HTTP endpoint(s) automatically. Configure via environment variables or `.env`:

```bash
# .env
WEBHOOK_URLS=http://localhost:8080/api/readings,http://localhost:9091/metrics/job/tuya
WEBHOOK_TIMEOUT=10
WEBHOOK_RETRIES=3
WEBHOOK_RETRY_DELAY=1.0
WEBHOOK_BATCH=true
POLL_INTERVAL=60
```

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_URLS` | *(empty)* | Comma-separated HTTP endpoints. Leave empty to disable webhooks |
| `WEBHOOK_TIMEOUT` | `10` | HTTP request timeout in seconds |
| `WEBHOOK_RETRIES` | `3` | Retry count per request on failure |
| `WEBHOOK_RETRY_DELAY` | `1.0` | Seconds between retries |
| `WEBHOOK_BATCH` | `true` | `true` = one POST per poll cycle with all readings. `false` = one POST per device |
| `POLL_INTERVAL` | `60` | Seconds between poll cycles (also usable as CLI arg: `serve 30`) |

### Webhook Payload

**Batch mode** (`WEBHOOK_BATCH=true`) — one POST per cycle:

```json
{
  "readings": [
    {
      "timestamp": "2026-05-01T14:30:00+0530",
      "device_name": "Zebronics_SP116",
      "device_id": "d714e8...",
      "ip": "192.168.1.2",
      "status": "online",
      "voltage_v": 240.8,
      "current_ma": 1177,
      "power_w": 173.0,
      "energy_wh": 0.029
    }
  ],
  "events": [
    {
      "timestamp": "...",
      "data": {"event": "power_restored", "device_name": "...", "outage_duration_seconds": 3600}
    }
  ]
}
```

**Individual mode** (`WEBHOOK_BATCH=false`) — one POST per device:

```json
{
  "reading": { "timestamp": "...", "device_name": "...", "voltage_v": 240.8, ... },
  "event": null
}
```

### Programmatic Usage

```python
from tuya import (
    load_devices, poll_devices, push_webhooks, WebhookConfig,
)

devices = load_devices()
config = WebhookConfig(
    urls=["http://localhost:8080/api/readings"],
    timeout=10,
    retries=3,
    batch=True,
)

results = poll_devices(devices, save=True)
stats = push_webhooks(results, config)
print(f"Sent: {stats['sent']}, Failed: {stats['failed']}")
```

## Docker

Run as an always-on service with Docker:

```bash
# Build and run
docker compose up -d

# View logs
docker compose logs -f tuya-poll

# Stop
docker compose down
```

### Prerequisites

1. Run `setup` locally first to create `data/devices.json` with your device keys
2. The Docker container uses `network_mode: host` — required for local device communication (Linux only)

### docker-compose.yml

```yaml
services:
  tuya-poll:
    build: .
    container_name: tuya-poll
    restart: unless-stopped
    network_mode: host
    env_file: .env
    environment:
      - POLL_INTERVAL=60
    volumes:
      - ./data:/app/data
```

### Environment Variables

Copy `.env.example` to `.env` and set:

```bash
# Required for setup/refresh only (container just polls)
CLIENTKEY="..."
CLIENTSECRET="..."
APIREGION="..."

# Webhook endpoints (optional)
WEBHOOK_URLS="http://your-dashboard:8080/api/readings"
POLL_INTERVAL=60
```

### Manual Docker Build

```bash
docker build -t tuya-poll .
docker run -d \
  --name tuya-poll \
  --network host \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  tuya-poll
```

> **Note:** `network_mode: host` is required because tinytuya uses UDP broadcast for device discovery and TCP to local device IPs. This only works on Linux Docker hosts. On macOS/Windows, run the service directly with `uv run python run.py serve`.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "plan expired" | Create a new Tuya developer account, then `refresh` |
| 0 devices found | Link your Smart Life app in the Tuya IoT project |
| Device timeout | Make sure device is on the same WiFi network |
| Error 914 / 904 | Run `scan` to update IPs, or set static IPs on router |
| Permission denied | Link app account to the correct project |
| Keys rotated | Run `refresh` with active cloud account |

---

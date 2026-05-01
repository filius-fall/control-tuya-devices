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

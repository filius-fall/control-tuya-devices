# Control Tuya Devices

Monitor power usage from Tuya smart switches via a web dashboard and export metrics to Prometheus.

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

You need the **Device Connection Service** and **Home Management** APIs enabled in your Tuya IoT project.

### 2. Device Discovery (optional)

Device discovery is manual. Refresh the cached device list and LAN metadata into SQLite with:

```bash
uv run tuya setup
```

This performs a cloud refresh and optional LAN scan, then stores the results in `tuya.db` for ongoing local polling.

## Usage

### Web Dashboard & Prometheus Exporter

Run the Flask app with gunicorn:

```bash
uv run gunicorn -w 1 -b 0.0.0.0:8000 tuya.web:app
```

Or use the provided Dockerfile:

```bash
docker compose up --build
```

**Routes:**

| Route | Description |
|-------|-------------|
| `/` | Device dashboard with power/current/voltage/energy readings |
| `/metrics` | Prometheus scrape endpoint |
| `/rooms` | Room assignment management |
| `/refresh` | Trigger manual device re-discovery and refresh the SQLite cache |

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `TUYA_POLL_INTERVAL` | `30` | Seconds between metric polls |
| `TUYA_DB_PATH` | `tuya.db` | Shared SQLite path for device cache, room overrides, status cache, and energy state |

### Dashboard Features

- **Real-time readings** — Power (W), current (A), voltage (V), cumulative energy (kWh)
- **Filters** — Search by name, filter by room, filter by on/off/online/offline
- **Sorting** — By name, room, power, current, voltage, energy
- **Room badges** — Auto-discovered from Tuya Cloud, or manually overridden
- **Device toggle** — Click any online device card to turn it on or off
- **No device IDs exposed** — Safe for screenshots

### Room Management

If the Tuya API doesn't return room data, assign rooms manually:

1. Open `/rooms` in your browser
2. Select devices via checkboxes (or "select all")
3. Enter a room name and click **Assign to Room**
4. Download the mapping as JSON for backup or to copy to another server
5. Upload a JSON mapping to restore or migrate assignments

Discovered devices, room overrides, cached statuses, and synthesized energy totals are stored together in SQLite (`tuya.db` by default) and survive restarts.

### CLI Commands

```bash
# Interactive device setup (TUI)
uv run tuya setup

# Live top view
uv run tuya-top

# One-shot status table
uv run tuya status

# List cached devices
uv run tuya list-devices
uv run tuya list-devices --refresh

# Fetch historic power data
uv run tuya history <device_id> --hours 24 --verbose

# Always-on polling with webhook push (no Flask needed)
uv run tuya serve
uv run tuya serve --interval 30
```

## Webhook Push

The `tuya serve` command and the Flask web app both push readings to HTTP endpoints. Configure via `.env`:

```bash
WEBHOOK_URLS="http://localhost:8080/api/readings,http://localhost:9091/metrics/job/tuya"
WEBHOOK_TIMEOUT=10
WEBHOOK_RETRIES=3
WEBHOOK_RETRY_DELAY=1.0
WEBHOOK_BATCH=true
```

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_URLS` | *(empty)* | Comma-separated HTTP endpoints. Leave empty to disable |
| `WEBHOOK_TIMEOUT` | `10` | HTTP request timeout in seconds |
| `WEBHOOK_RETRIES` | `3` | Retry count per request on failure |
| `WEBHOOK_RETRY_DELAY` | `1.0` | Seconds between retries |
| `WEBHOOK_BATCH` | `true` | `true` = one POST per poll cycle. `false` = one POST per device |

### Webhook Payload

**Batch mode** (`WEBHOOK_BATCH=true`):

```json
{
  "readings": [
    {"id": "...", "name": "...", "online": true, "power": "166.0 W", ...}
  ]
}
```

**Individual mode** (`WEBHOOK_BATCH=false`):

```json
{
  "reading": {"id": "...", "name": "...", "online": true, "power": "166.0 W", ...}
}
```

## Power Outage Tracking

The system tracks online/offline transitions and logs power outage events:

- **`power_lost`** — logged when a device goes offline
- **`power_restored`** — logged when a device comes back online, includes outage duration

Outage state is persisted in SQLite and survives restarts. Events are included in webhook payloads.

## Prometheus Integration

Add this job to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: tuya
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: /metrics
```

### Available Metrics

All live device metrics use the stable `device_id` label. Human-readable metadata is exposed separately via `tuya_device_info{device_id,device,room}` so renames and room moves do not break metric continuity.

| Metric | Type | Description |
|--------|------|-------------|
| `tuya_power_watts` | Gauge | Current power draw |
| `tuya_current_amps` | Gauge | Current current |
| `tuya_voltage_volts` | Gauge | Current voltage |
| `tuya_energy_kwh` | Gauge | Raw device-reported cumulative energy for the current day (resets at midnight) |
| `tuya_energy_joules_total` | Counter | Exporter-maintained monotonic total energy synthesized from the daily-reset device meter |
| `tuya_energy_resets_total` | Counter | Number of daily energy counter resets detected by the exporter |
| `tuya_online` | Gauge | Device reachability (1 = online, 0 = offline) |
| `tuya_switch_state` | Gauge | Relay state (1 = on, 0 = off, `NaN` = unknown/offline) |
| `tuya_device_info` | Gauge | Info metric for joining `device_id` to current `device` and `room` labels |

**Recommended queries**

- Hourly energy in kWh:
  ```promql
  increase(tuya_energy_joules_total[1h]) / 3.6e6
  ```
- Energy by room in kWh:
  ```promql
  sum by (room) (
    increase(tuya_energy_joules_total[1h])
      * on (device_id) group_left(device, room) tuya_device_info
  ) / 3.6e6
  ```
- Device-reported usage so far today:
  ```promql
  tuya_energy_kwh
  ```

## Deployment

### Docker Compose

```bash
docker compose up -d
```

The compose file uses `network_mode: host` — required for local device polling (tinytuya uses UDP broadcast + TCP to device IPs). This works on Linux Docker hosts only.

The bundled compose file persists exporter state in `./data/tuya.db`.

No separate `switches.toml` is required; device metadata is cached in SQLite.

### systemd

A sample service file is in `deploy/tuya-exporter.service`. Copy and adapt the `WorkingDirectory`, `EnvironmentFile`, and `ExecStart` paths.

### Ansible

An Ansible role is in `deploy/ansible/roles/tuya_exporter/`. Import it into your playbook:

```yaml
- hosts: monitoring
  roles:
    - role: tuya_exporter
```

## Tested Devices

These devices have been confirmed working with local-only polling:

| Device | Category | Protocol Version | Notes |
|--------|----------|-----------------|-------|
| **Zebronics ZEB-SP116** | Smart Plug | v3.4 | Uses numeric DPS codes (1, 20, 22, 25). Fully working — power, current, voltage, toggle. |
| **10Amp Smart Plug** (generic) | Smart Plug | v3.3 | Standard string DPS codes (`cur_power`, `cur_current`, `cur_voltage`). Fully working. |

PRs welcome to add more devices. If you test a new device, please include the protocol version and whether it uses numeric or string DPS codes.

## Project Structure

```
.
├── tuya/
│   ├── api_client.py      # Tuya Cloud API wrapper
│   ├── room_config.py     # SQLite room override storage
│   ├── web.py             # Flask dashboard + Prometheus exporter
│   ├── local_client.py    # Direct LAN device polling (auto-retry versions)
│   ├── webhook.py         # Push readings to HTTP endpoints
│   ├── outage.py          # Power outage tracking (lost/restored events)
│   ├── energy_tracker.py  # Persistent energy tracking with daily-reset handling
│   ├── device_store.py    # SQLite device/status cache
│   ├── state_db.py        # Shared SQLite connection
│   ├── logger.py          # Structured logging
│   ├── cli.py             # argparse CLI entry point
│   ├── top.py             # Live-updating top view
│   ├── rich_output.py     # Rich console formatting
│   ├── history.py         # Power log summarization
│   └── templates/
│       ├── index.html     # Dashboard
│       └── rooms.html     # Room management
├── deploy/
│   ├── docker-compose.yml
│   └── ansible/           # Ansible role
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── tuya.db                # Shared SQLite device/status/room/energy state (gitignored)
└── .env                   # API credentials (gitignored)
```

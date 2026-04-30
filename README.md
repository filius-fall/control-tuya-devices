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
```

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

## Project Structure

```
.
├── tuya/
│   ├── api_client.py      # Tuya Cloud API wrapper
│   ├── room_config.py     # SQLite room override storage
│   ├── web.py             # Flask dashboard + Prometheus exporter
│   ├── local_client.py    # Direct LAN device polling
│   ├── logger.py          # Structured logging
│   ├── top.py             # Live-updating top view
│   └── templates/
│       ├── index.html     # Dashboard
│       └── rooms.html     # Room management
├── deploy/
│   ├── docker-compose.yml
│   └── ansible/           # Ansible role
├── Dockerfile
├── pyproject.toml
├── tuya.db                # Shared SQLite device/status/room/energy state (gitignored)
└── .env                   # API credentials (gitignored)
```

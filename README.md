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

The exporter auto-discovers all devices from the Tuya Cloud every hour. No manual configuration is required for cloud polling.

If you want faster local LAN polling, generate a `switches.toml`:

```bash
uv run tuya setup
```

This opens an interactive TUI where you can select devices and write their local credentials. `switches.toml` is gitignored.

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
| `/refresh` | Trigger immediate device re-discovery |

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `TUYA_POLL_INTERVAL` | `30` | Seconds between metric polls |
| `TUYA_DISCOVER_INTERVAL` | `3600` | Seconds between device re-discovery (`0` to disable) |
| `TUYA_ROOM_DB` | `rooms.db` | SQLite path for room overrides |

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

Room overrides are stored in SQLite (`rooms.db` by default) and survive restarts.

### CLI Commands

```bash
# Interactive device setup (TUI)
uv run tuya setup

# Live top view
uv run tuya-top

# One-shot status table
uv run tuya status

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

All metrics include `device` and `room` labels:

| Metric | Type | Description |
|--------|------|-------------|
| `tuya_power_watts` | Gauge | Current power draw |
| `tuya_current_amps` | Gauge | Current current |
| `tuya_voltage_volts` | Gauge | Current voltage |
| `tuya_energy_kwh` | Counter | Cumulative energy (resets at midnight) |
| `tuya_online` | Gauge | Device reachability (1 = online) |
| `tuya_switch_state` | Gauge | Relay state (1 = on, 0 = off) |

**Grafana tip:** Use `increase(tuya_energy_kwh[1h])` to get hourly consumption. The Counter type handles midnight resets automatically.

## Deployment

### Docker Compose

```bash
docker compose up -d
```

Optional: mount a local `switches.toml` for LAN polling:

```yaml
volumes:
  - ./switches.toml:/app/switches.toml:ro
```

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
├── switches.toml          # Optional LAN config (gitignored)
├── rooms.db               # Room overrides (gitignored)
└── .env                   # API credentials (gitignored)
```

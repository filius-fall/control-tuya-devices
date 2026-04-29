"""Prometheus metrics exporter for Tuya devices.

Usage with gunicorn:
    gunicorn -w 1 -b 0.0.0.0:8000 tuya.metrics_exporter:app

The background polling thread runs in the worker process and updates
metrics that are served via the WSGI app.

Auto-discovers all devices from the Tuya Cloud. Uses local_key + ip
from switches.toml when available for local polling, otherwise falls
back to cloud polling.
"""

import threading
import time
import os

from prometheus_client import Gauge, Counter, make_wsgi_app
from prometheus_client.registry import CollectorRegistry

from . import logger
from . import api_client
from . import local_client
from . import devices as device_config

log = logger.logs

POLL_INTERVAL = int(os.getenv("TUYA_POLL_INTERVAL", "30"))
DISCOVER_INTERVAL = int(os.getenv("TUYA_DISCOVER_INTERVAL", "300"))  # 5 minutes

REGISTRY = CollectorRegistry()

POWER = Gauge(
    "tuya_power_watts",
    "Current power draw",
    ["device"],
    registry=REGISTRY,
)

CURRENT = Gauge(
    "tuya_current_amps",
    "Current current",
    ["device"],
    registry=REGISTRY,
)

VOLTAGE = Gauge(
    "tuya_voltage_volts",
    "Current voltage",
    ["device"],
    registry=REGISTRY,
)

ENERGY = Counter(
    "tuya_energy_kwh",
    "Cumulative energy consumption (resets at midnight)",
    ["device"],
    registry=REGISTRY,
)

ONLINE = Gauge(
    "tuya_online",
    "Device is reachable (1=yes, 0=no)",
    ["device"],
    registry=REGISTRY,
)

SWITCH = Gauge(
    "tuya_switch_state",
    "Relay state (1=on, 0=off)",
    ["device"],
    registry=REGISTRY,
)

# Cached device list from cloud + local config overrides
_cloud_devices: list[dict] = []
_local_config: dict[str, dict] = {}
_local_config_mtime: float = 0.0
_prev_energy: dict[str, float] = {}


def _load_local_config() -> dict[str, dict]:
    """Load switches.toml and return a dict keyed by device id."""
    import os as _os

    path = "switches.toml"
    mtime = 0.0
    try:
        mtime = _os.path.getmtime(path)
    except OSError:
        return {}

    global _local_config_mtime
    if mtime == _local_config_mtime:
        return _local_config

    switches = device_config.load_switches(path)
    _local_config_mtime = mtime
    return {sw.get("id"): sw for sw in switches if sw.get("id")}


def _discover_devices() -> list[dict]:
    """Fetch device list from Tuya Cloud."""
    try:
        return api_client.get_devices()
    except Exception:
        log.error("Device discovery failed", exc_info=True)
        return []


def _poll_device(dev: dict) -> None:
    """Poll a single device and update metrics."""
    dev_id = dev.get("id", "")
    name = dev.get("name", "unknown")
    version = dev.get("version", "3.3")

    # Check if local config exists for this device
    local_cfg = _local_config.get(dev_id, {})
    local_key = local_cfg.get("local_key")
    ip = local_cfg.get("ip")

    dps = None
    source = "cloud"
    online = False

    if local_key and ip:
        local_status = local_client.get_device_status_local(
            dev_id, local_key, ip, version
        )
        if local_status and "dps" in local_status:
            dps = local_status["dps"]
            source = "local"
            online = True

    if dps is None:
        cloud_status = api_client.get_device_status(dev_id)
        if cloud_status and isinstance(cloud_status, dict):
            online = True
            result = cloud_status.get("result", [])
            if isinstance(result, list):
                dps = {
                    item["code"]: item.get("value")
                    for item in result
                    if isinstance(item, dict) and "code" in item
                }
            elif isinstance(result, dict):
                dps = result
            else:
                dps = {}

    if not dps:
        ONLINE.labels(device=name).set(0)
        return

    ONLINE.labels(device=name).set(1)

    # Power (deciwatts -> watts)
    raw_power = dps.get("cur_power") or dps.get("Power")
    if raw_power is not None:
        try:
            POWER.labels(device=name).set(float(raw_power) / 10)
        except (ValueError, TypeError):
            pass

    # Current (mA -> A)
    raw_current = dps.get("cur_current") or dps.get("Current")
    if raw_current is not None:
        try:
            CURRENT.labels(device=name).set(float(raw_current) / 1000)
        except (ValueError, TypeError):
            pass

    # Voltage (decivolts -> V)
    raw_voltage = dps.get("cur_voltage") or dps.get("Voltage")
    if raw_voltage is not None:
        try:
            VOLTAGE.labels(device=name).set(float(raw_voltage) / 10)
        except (ValueError, TypeError):
            pass

    # Energy (0.1 kWh -> kWh, counter with reset handling)
    raw_energy = dps.get("add_ele") or dps.get("total_power")
    _update_energy(name, raw_energy)

    # Switch state
    switch_state = dps.get("switch_1") or dps.get("switch") or dps.get("led_switch")
    if switch_state is True:
        SWITCH.labels(device=name).set(1)
    elif switch_state is False:
        SWITCH.labels(device=name).set(0)

    log.info(
        "Polled device",
        device=name,
        source=source,
        power=raw_power,
        current=raw_current,
        voltage=raw_voltage,
        energy=raw_energy,
    )


def _update_energy(device_name: str, raw: float | None) -> None:
    """Update the energy counter, handling midnight resets."""
    if raw is None:
        return
    try:
        current = float(raw) / 10
    except (ValueError, TypeError):
        return

    prev = _prev_energy.get(device_name)
    if prev is None:
        _prev_energy[device_name] = current
        return

    if current >= prev:
        delta = current - prev
    else:
        delta = current

    if delta > 0:
        ENERGY.labels(device=device_name).inc(delta)
        _prev_energy[device_name] = current


def _poll_all():
    """Poll all discovered devices."""
    global _cloud_devices, _local_config

    _local_config = _load_local_config()

    if not _cloud_devices:
        _cloud_devices = _discover_devices()
        log.info("Discovered devices", count=len(_cloud_devices))

    for dev in _cloud_devices:
        try:
            _poll_device(dev)
        except Exception:
            log.error("Poll failed", device=dev.get("name"), exc_info=True)


def _polling_loop():
    """Background thread that polls devices continuously."""
    log.info("Starting metrics polling loop", interval_seconds=POLL_INTERVAL)
    last_discover = 0.0
    while True:
        try:
            now = time.time()
            if now - last_discover >= DISCOVER_INTERVAL:
                _cloud_devices = _discover_devices()
                log.info("Refreshed device list", count=len(_cloud_devices))
                last_discover = now
            _poll_all()
        except Exception:
            log.error("Polling loop error", exc_info=True)
        time.sleep(POLL_INTERVAL)


_polling_thread = threading.Thread(target=_polling_loop, daemon=True)
_polling_thread.start()

app = make_wsgi_app(registry=REGISTRY)

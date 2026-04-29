"""Flask web UI and Prometheus metrics exporter for Tuya devices.

Usage with gunicorn:
    gunicorn -w 1 -b 0.0.0.0:8000 tuya.web:app

Routes:
    /              — Device dashboard
    /refresh       — Trigger device re-discovery
    /poll/<id>     — JSON with current device stats
    /metrics       — Prometheus scrape endpoint
"""

import threading
import time
import os

from flask import Flask, render_template, jsonify, redirect, url_for
from prometheus_client import Gauge, Counter, make_wsgi_app
from prometheus_client.registry import CollectorRegistry
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from . import logger
from . import api_client
from . import local_client
from . import devices as device_config
from .rich_output import (
    _extract_power_dps,
    _fmt_power,
    _fmt_current,
    _fmt_voltage,
    _fmt_energy,
)

log = logger.logs

POLL_INTERVAL = int(os.getenv("TUYA_POLL_INTERVAL", "30"))
DISCOVER_INTERVAL = int(os.getenv("TUYA_DISCOVER_INTERVAL", "3600"))

REGISTRY = CollectorRegistry()

POWER = Gauge("tuya_power_watts", "Current power draw", ["device"], registry=REGISTRY)
CURRENT = Gauge("tuya_current_amps", "Current current", ["device"], registry=REGISTRY)
VOLTAGE = Gauge("tuya_voltage_volts", "Current voltage", ["device"], registry=REGISTRY)
ENERGY = Counter(
    "tuya_energy_kwh",
    "Cumulative energy consumption (resets at midnight)",
    ["device"],
    registry=REGISTRY,
)
ONLINE = Gauge(
    "tuya_online", "Device is reachable (1=yes, 0=no)", ["device"], registry=REGISTRY
)
SWITCH = Gauge(
    "tuya_switch_state", "Relay state (1=on, 0=off)", ["device"], registry=REGISTRY
)

_cloud_devices: list[dict] = []
_local_config: dict[str, dict] = {}
_local_config_mtime: float = 0.0
_prev_energy: dict[str, float] = {}
_prometheus_app = make_wsgi_app(registry=REGISTRY)


def _load_local_config() -> dict[str, dict]:
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
    try:
        return api_client.get_devices()
    except Exception:
        log.error("Device discovery failed", exc_info=True)
        return []


def _poll_device(dev: dict) -> dict:
    """Poll a single device and return a status dict."""
    dev_id = dev.get("id", "")
    name = dev.get("name", "unknown")
    version = dev.get("version", "3.3")
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
        return {
            "id": dev_id,
            "name": name,
            "online": False,
            "source": "—",
        }

    ONLINE.labels(device=name).set(1)

    raw_power = dps.get("cur_power") or dps.get("Power")
    if raw_power is not None:
        try:
            POWER.labels(device=name).set(float(raw_power) / 10)
        except (ValueError, TypeError):
            pass

    raw_current = dps.get("cur_current") or dps.get("Current")
    if raw_current is not None:
        try:
            CURRENT.labels(device=name).set(float(raw_current) / 1000)
        except (ValueError, TypeError):
            pass

    raw_voltage = dps.get("cur_voltage") or dps.get("Voltage")
    if raw_voltage is not None:
        try:
            VOLTAGE.labels(device=name).set(float(raw_voltage) / 10)
        except (ValueError, TypeError):
            pass

    raw_energy = dps.get("add_ele") or dps.get("total_power")
    _update_energy(name, raw_energy)

    switch_state = dps.get("switch_1") or dps.get("switch") or dps.get("led_switch")
    if switch_state is True:
        SWITCH.labels(device=name).set(1)
    elif switch_state is False:
        SWITCH.labels(device=name).set(0)

    power_dps = _extract_power_dps(dps)

    return {
        "id": dev_id,
        "name": name,
        "online": True,
        "source": source,
        "on": switch_state is True,
        "power": _fmt_power(power_dps.get("power")),
        "current": _fmt_current(power_dps.get("current")),
        "voltage": _fmt_voltage(power_dps.get("voltage")),
        "energy": _fmt_energy(power_dps.get("energy")),
    }


def _update_energy(device_name: str, raw: float | None) -> None:
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

    delta = current - prev if current >= prev else current
    if delta > 0:
        ENERGY.labels(device=device_name).inc(delta)
        _prev_energy[device_name] = current


def _poll_all():
    global _cloud_devices, _local_config
    _local_config = _load_local_config()

    if not _cloud_devices:
        _cloud_devices = _discover_devices()
        log.info("Discovered devices", count=len(_cloud_devices))

    statuses = []
    for dev in _cloud_devices:
        try:
            statuses.append(_poll_device(dev))
        except Exception:
            log.error("Poll failed", device=dev.get("name"), exc_info=True)
            statuses.append(
                {
                    "id": dev.get("id", ""),
                    "name": dev.get("name", "unknown"),
                    "online": False,
                    "source": "—",
                }
            )
    return statuses


def _polling_loop():
    log.info("Starting metrics polling loop", interval_seconds=POLL_INTERVAL)
    last_discover = 0.0
    while True:
        try:
            now = time.time()
            if DISCOVER_INTERVAL > 0 and now - last_discover >= DISCOVER_INTERVAL:
                _cloud_devices = _discover_devices()
                log.info("Refreshed device list", count=len(_cloud_devices))
                last_discover = now
            _poll_all()
        except Exception:
            log.error("Polling loop error", exc_info=True)
        time.sleep(POLL_INTERVAL)


_polling_thread = threading.Thread(target=_polling_loop, daemon=True)
_polling_thread.start()

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

flask_app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)


@flask_app.route("/")
def index():
    statuses = _poll_all()
    online_count = sum(1 for s in statuses if s.get("online"))
    return render_template(
        "index.html",
        devices=statuses,
        online_count=online_count,
        total_count=len(statuses),
        poll_interval=POLL_INTERVAL,
        discover_interval=DISCOVER_INTERVAL,
    )


@flask_app.route("/refresh", methods=["POST"])
def refresh():
    global _cloud_devices
    _cloud_devices = _discover_devices()
    log.info("Manual device refresh", count=len(_cloud_devices))
    return redirect(url_for("index"))


@flask_app.route("/poll/<device_id>")
def poll_device(device_id):
    for dev in _cloud_devices:
        if dev.get("id") == device_id:
            return jsonify(_poll_device(dev))
    return jsonify({"error": "Device not found"}), 404


# Mount Prometheus metrics at /metrics
app = DispatcherMiddleware(
    flask_app,
    {"/metrics": _prometheus_app},
)

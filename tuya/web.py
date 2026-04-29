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
import json
import io
from datetime import datetime, timezone

from flask import (
    Flask,
    render_template,
    jsonify,
    redirect,
    url_for,
    request,
    send_file,
    Response,
)
from prometheus_client import Gauge, Counter, make_wsgi_app
from prometheus_client.registry import CollectorRegistry

from . import logger
from . import api_client
from . import local_client
from . import devices as device_config
from . import room_config
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

POWER = Gauge(
    "tuya_power_watts", "Current power draw", ["device", "room"], registry=REGISTRY
)
CURRENT = Gauge(
    "tuya_current_amps", "Current current", ["device", "room"], registry=REGISTRY
)
VOLTAGE = Gauge(
    "tuya_voltage_volts", "Current voltage", ["device", "room"], registry=REGISTRY
)
ENERGY = Counter(
    "tuya_energy_kwh",
    "Cumulative energy consumption (resets at midnight)",
    ["device", "room"],
    registry=REGISTRY,
)
ONLINE = Gauge(
    "tuya_online",
    "Device is reachable (1=yes, 0=no)",
    ["device", "room"],
    registry=REGISTRY,
)
SWITCH = Gauge(
    "tuya_switch_state",
    "Relay state (1=on, 0=off)",
    ["device", "room"],
    registry=REGISTRY,
)

_cloud_devices: list[dict] = []
_device_rooms: dict[str, str] = {}
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
    global _device_rooms
    try:
        devices = api_client.get_devices()
    except Exception:
        log.error("Device discovery failed", exc_info=True)
        return []
    try:
        _device_rooms = api_client.get_device_room_map()
    except Exception:
        log.error("Room mapping failed", exc_info=True)
        _device_rooms = {}
    return devices


def _resolve_room(dev_id: str) -> str:
    """Return the effective room for a device (override > API > unknown)."""
    return room_config.resolve_room(dev_id, _device_rooms.get(dev_id))


def _extract_dps_from_status(status: dict | None) -> dict | None:
    """Extract DPs from a Tuya Cloud status response, or None if offline."""
    if not status or not isinstance(status, dict):
        return None

    # API error / device explicitly offline
    if not status.get("success", True):
        return None

    result = status.get("result")
    if result is None:
        return None

    # Result is a list of {code, value} — the common format
    if isinstance(result, list):
        return {
            item["code"]: item.get("value")
            for item in result
            if isinstance(item, dict) and "code" in item
        }

    # Result is a dict — may contain an "online" flag and "status" array
    if isinstance(result, dict):
        if result.get("online") is False:
            return None
        status_list = result.get("status") or result.get("result") or []
        if isinstance(status_list, list):
            return {
                item["code"]: item.get("value")
                for item in status_list
                if isinstance(item, dict) and "code" in item
            }
        return result

    return None


def _mark_device_offline(name: str, room: str) -> None:
    """Set all gauges to offline state and clear stale metric values."""
    ONLINE.labels(device=name, room=room).set(0)
    POWER.labels(device=name, room=room).set(0)
    CURRENT.labels(device=name, room=room).set(0)
    VOLTAGE.labels(device=name, room=room).set(0)


def _poll_device(dev: dict) -> dict:
    """Poll a single device and return a status dict."""
    dev_id = dev.get("id", "")
    name = dev.get("name", "unknown")
    room = _resolve_room(dev_id)
    version = dev.get("version", "3.3")
    local_cfg = _local_config.get(dev_id, {})
    local_key = local_cfg.get("local_key")
    ip = local_cfg.get("ip")

    # Use the online flag from the discovery list if the cloud already knows
    # the device is offline.
    if dev.get("online") is False:
        _mark_device_offline(name, room)
        return {
            "id": dev_id,
            "name": name,
            "room": room,
            "online": False,
            "source": "—",
        }

    dps = None
    source = "cloud"

    try:
        if local_key and ip:
            local_status = local_client.get_device_status_local(
                dev_id, local_key, ip, version
            )
            if local_status and "dps" in local_status:
                dps = local_status["dps"]
                source = "local"
    except Exception:
        log.warning("Local poll failed", device_id=dev_id, exc_info=True)

    if dps is None:
        try:
            cloud_status = api_client.get_device_status(dev_id)
            dps = _extract_dps_from_status(cloud_status)
        except Exception:
            log.warning("Cloud poll failed", device_id=dev_id, exc_info=True)

    # Some offline devices return a non-empty status with all-null values.
    if dps and all(v is None for v in dps.values()):
        dps = None

    if not dps:
        _mark_device_offline(name, room)
        return {
            "id": dev_id,
            "name": name,
            "room": room,
            "online": False,
            "source": "—",
        }

    ONLINE.labels(device=name, room=room).set(1)

    raw_power = dps.get("cur_power") or dps.get("Power")
    if raw_power is not None:
        try:
            POWER.labels(device=name, room=room).set(float(raw_power) / 10)
        except (ValueError, TypeError):
            pass

    raw_current = dps.get("cur_current") or dps.get("Current")
    if raw_current is not None:
        try:
            CURRENT.labels(device=name, room=room).set(float(raw_current) / 1000)
        except (ValueError, TypeError):
            pass

    raw_voltage = dps.get("cur_voltage") or dps.get("Voltage")
    if raw_voltage is not None:
        try:
            VOLTAGE.labels(device=name, room=room).set(float(raw_voltage) / 10)
        except (ValueError, TypeError):
            pass

    raw_energy = _extract_power_dps(dps).get("energy")
    log.debug(
        "_poll_device energy",
        device=name,
        raw_energy=raw_energy,
        dps_keys=list(dps.keys()),
    )
    _update_energy(name, room, raw_energy)

    # Use key-in-dict check so a literal False value is not skipped by `or`.
    switch_state: bool | None = None
    for code in ("switch_1", "switch", "led_switch"):
        if code in dps:
            switch_state = bool(dps[code])
            break

    if switch_state is True:
        SWITCH.labels(device=name, room=room).set(1)
    elif switch_state is False:
        SWITCH.labels(device=name, room=room).set(0)

    power_dps = _extract_power_dps(dps)

    return {
        "id": dev_id,
        "name": name,
        "room": room,
        "online": True,
        "source": source,
        "on": switch_state is True,
        "power": _fmt_power(power_dps.get("power")),
        "current": _fmt_current(power_dps.get("current")),
        "voltage": _fmt_voltage(power_dps.get("voltage")),
        "energy": _fmt_energy(power_dps.get("energy")),
    }


def _update_energy(device_name: str, room: str, raw: float | None) -> None:
    if raw is None:
        log.debug("_update_energy: raw is None", device=device_name)
        return
    try:
        current = float(raw) / 10
    except (ValueError, TypeError):
        log.debug("_update_energy: bad raw value", device=device_name, raw=raw)
        return

    prev = _prev_energy.get(device_name)
    if prev is None:
        _prev_energy[device_name] = current
        # Initialize the counter so it appears in /metrics immediately.
        ENERGY.labels(device=device_name, room=room).inc(0)
        log.debug("_update_energy: baseline set", device=device_name, current=current)
        return

    delta = current - prev if current >= prev else current
    log.debug(
        "_update_energy: delta check",
        device=device_name,
        prev=prev,
        current=current,
        delta=delta,
    )
    if delta > 0:
        ENERGY.labels(device=device_name, room=room).inc(delta)
        _prev_energy[device_name] = current
        log.debug("_update_energy: incremented", device=device_name, delta=delta)


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
                    "room": _resolve_room(dev.get("id", "")),
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
    """Render the dashboard skeleton; actual device data is fetched via /statuses."""
    if not _cloud_devices:
        _cloud_devices[:] = _discover_devices()

    devices = []
    rooms = set()
    for dev in _cloud_devices:
        dev_id = dev.get("id", "")
        room = _resolve_room(dev_id)
        rooms.add(room)
        devices.append(
            {
                "id": dev_id,
                "name": dev.get("name", "unknown"),
                "room": room,
            }
        )

    return render_template(
        "index.html",
        devices=devices,
        rooms=sorted(rooms),
        online_count=0,
        total_count=len(devices),
        poll_interval=POLL_INTERVAL,
        discover_interval=DISCOVER_INTERVAL,
    )


@flask_app.route("/statuses")
def statuses_json():
    """Return current device statuses as JSON for async dashboard updates."""
    return jsonify(_poll_all())


@flask_app.route("/refresh", methods=["POST"])
def refresh():
    global _cloud_devices
    _cloud_devices = _discover_devices()
    log.info("Manual device refresh", count=len(_cloud_devices))
    return redirect(url_for("index"))


def _get_switch_codes(device_id: str) -> list[str]:
    """Return all switch DP codes a device exposes, ordered by preference."""
    status = api_client.get_device_status(device_id)
    if not status or not isinstance(status, dict):
        return []
    result = status.get("result", [])
    codes: set[str] = set()
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and "code" in item:
                codes.add(item["code"])
    elif isinstance(result, dict):
        if isinstance(result.get("status"), list):
            for item in result["status"]:
                if isinstance(item, dict) and "code" in item:
                    codes.add(item["code"])
        else:
            codes.update(result.keys())
    ordered = []
    for code in ("switch_1", "switch", "led_switch"):
        if code in codes:
            ordered.append(code)
    return ordered


def _try_toggle(device_id: str, state: bool) -> None:
    """Send a toggle command, trying fallback switch codes on failure."""
    codes = _get_switch_codes(device_id)
    if not codes:
        raise RuntimeError("No switch codes found for device")

    last_error = None
    for code in codes:
        try:
            api_client.send_device_command(
                device_id, [{"code": code, "value": bool(state)}]
            )
            log.info(
                "Toggled device", device_id=device_id, state=bool(state), code=code
            )
            return
        except Exception as exc:
            last_error = exc
            log.warning(
                "Toggle attempt failed",
                device_id=device_id,
                code=code,
                error=str(exc),
            )

    raise last_error or RuntimeError("All toggle attempts failed")


@flask_app.route("/toggle/<device_id>", methods=["POST"])
def toggle_device(device_id):
    """Toggle a device on or off."""
    payload = request.get_json(force=True, silent=True) or {}
    state = payload.get("state")
    if state is None:
        return jsonify({"error": "Missing state"}), 400

    try:
        _try_toggle(device_id, bool(state))
        return jsonify({"success": True, "state": bool(state)})
    except Exception:
        log.error("Toggle failed", device_id=device_id, exc_info=True)
        return jsonify({"error": "Toggle failed"}), 500


@flask_app.route("/poll/<device_id>")
def poll_device(device_id):
    for dev in _cloud_devices:
        if dev.get("id") == device_id:
            return jsonify(_poll_device(dev))
    return jsonify({"error": "Device not found"}), 404


@flask_app.route("/rooms")
def rooms_page():
    """Room assignment management page."""
    devices_with_rooms = []
    for dev in _cloud_devices:
        dev_id = dev.get("id", "")
        devices_with_rooms.append(
            {
                "id": dev_id,
                "name": dev.get("name", "unknown"),
                "room": _resolve_room(dev_id),
            }
        )
    all_rooms = sorted(
        {d["room"] for d in devices_with_rooms if d["room"] != "unknown"}
        | set(room_config.get_overrides().values())
    )
    return render_template(
        "rooms.html",
        devices=devices_with_rooms,
        rooms=all_rooms,
    )


@flask_app.route("/rooms/assign", methods=["POST"])
def assign_rooms():
    """Bulk-assign selected devices to a room."""
    device_ids = request.form.getlist("device_ids")
    room_name = request.form.get("room_name", "").strip()

    if device_ids and room_name:
        mapping = {dev_id: room_name for dev_id in device_ids}
        room_config.set_rooms(mapping)
        log.info("Assigned devices to room", room=room_name, count=len(device_ids))

    return redirect(url_for("rooms_page"))


@flask_app.route("/rooms/clear", methods=["POST"])
def clear_room():
    """Remove the room override for a single device."""
    device_id = request.form.get("device_id", "").strip()
    if device_id:
        room_config.delete_room(device_id)
        log.info("Cleared room override", device_id=device_id)

    return redirect(url_for("rooms_page"))


@flask_app.route("/rooms/download")
def download_rooms():
    """Download room overrides as JSON."""
    mapping = room_config.get_overrides()
    data = json.dumps(mapping, indent=2, sort_keys=True)
    buf = io.BytesIO(data.encode("utf-8"))
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return send_file(
        buf,
        mimetype="application/json",
        as_attachment=True,
        download_name=f"tuya-rooms-{ts}.json",
    )


@flask_app.route("/rooms/upload", methods=["POST"])
def upload_rooms():
    """Upload room overrides from JSON."""
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided"}), 400

    try:
        data = json.load(file)
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Invalid JSON: {e}"}), 400

    if not isinstance(data, dict):
        return jsonify(
            {"error": "JSON must be an object mapping device_id to room_name"}
        ), 400

    # Filter to string values only
    mapping = {
        str(k): str(v) for k, v in data.items() if isinstance(v, (str, int, float))
    }

    room_config.set_rooms(mapping)
    log.info("Uploaded room overrides", count=len(mapping))
    return redirect(url_for("rooms_page"))


@flask_app.route("/metrics")
def metrics():
    """Prometheus scrape endpoint."""
    status_headers = []

    def start_response(status, headers):
        status_headers[:] = [status, headers]

    body = b"".join(_prometheus_app(request.environ, start_response))
    status = status_headers[0]
    headers = status_headers[1]
    return Response(body, status=status, headers=dict(headers))


app = flask_app

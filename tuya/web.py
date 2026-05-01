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
from prometheus_client import Gauge, make_wsgi_app
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.registry import CollectorRegistry

from . import logger
from . import api_client
from . import local_client
from . import room_config
from . import device_store
from .energy_tracker import EnergyTracker
from .outage import track_outage
from .rich_output import (
    _extract_power_dps,
    _fmt_power,
    _fmt_current,
    _fmt_voltage,
    _fmt_energy,
)

log = logger.logs

POLL_INTERVAL = int(os.getenv("TUYA_POLL_INTERVAL", "30"))
DISCOVER_INTERVAL = int(os.getenv("TUYA_DISCOVER_INTERVAL", "0"))

REGISTRY = CollectorRegistry()
METRIC_LABELS = ["device_id"]

POWER = Gauge(
    "tuya_power_watts", "Current power draw", METRIC_LABELS, registry=REGISTRY
)
CURRENT = Gauge(
    "tuya_current_amps", "Current current", METRIC_LABELS, registry=REGISTRY
)
VOLTAGE = Gauge(
    "tuya_voltage_volts", "Current voltage", METRIC_LABELS, registry=REGISTRY
)
ONLINE = Gauge(
    "tuya_online",
    "Device is reachable (1=yes, 0=no)",
    METRIC_LABELS,
    registry=REGISTRY,
)
SWITCH = Gauge(
    "tuya_switch_state",
    "Relay state (1=on, 0=off)",
    METRIC_LABELS,
    registry=REGISTRY,
)

_energy_tracker = EnergyTracker()
_last_refresh_error: str | None = None


def _metric_labels(device_id: str) -> dict[str, str]:
    return {"device_id": device_id}


class _ExporterStateCollector:
    def collect(self):
        device_info = GaugeMetricFamily(
            "tuya_device_info",
            "Device metadata for joining stable device_id metrics to human-readable labels",
            labels=["device_id", "device", "room"],
        )
        energy_today = GaugeMetricFamily(
            "tuya_energy_kwh",
            "Device-reported cumulative energy for the current day (resets at midnight)",
            labels=METRIC_LABELS,
        )
        energy_total = CounterMetricFamily(
            "tuya_energy_joules_total",
            "Exporter-maintained total energy consumption synthesized from the device daily meter",
            labels=METRIC_LABELS,
        )
        energy_resets = CounterMetricFamily(
            "tuya_energy_resets_total",
            "Number of device energy counter resets detected by the exporter",
            labels=METRIC_LABELS,
        )

        devices = device_store.get_devices()
        states = _energy_tracker.snapshot()

        for dev in devices:
            dev_id = dev.get("id", "")
            if not dev_id:
                continue
            device_info.add_metric(
                [dev_id, dev.get("name", "unknown"), _resolve_room(dev_id)], 1
            )

        for device_id in sorted(set(states) | {dev.get("id", "") for dev in devices}):
            if not device_id:
                continue
            state = states.get(device_id)
            energy_total.add_metric([device_id], state.total_joules if state else 0.0)
            energy_resets.add_metric(
                [device_id], float(state.reset_count) if state else 0.0
            )
            if state and state.last_raw_kwh is not None:
                energy_today.add_metric([device_id], state.last_raw_kwh)

        yield device_info
        yield energy_today
        yield energy_total
        yield energy_resets


REGISTRY.register(_ExporterStateCollector())
_prometheus_app = make_wsgi_app(registry=REGISTRY)


def _discover_devices() -> list[dict]:
    devices = api_client.get_devices()
    try:
        device_rooms = api_client.get_device_room_map()
    except Exception:
        log.error("Room mapping failed", exc_info=True)
        device_rooms = {}
    device_store.upsert_devices(devices, device_rooms)
    return device_store.get_devices()


def _resolve_room(dev_id: str) -> str:
    """Return the effective room for a device (override > cached discovery > unknown)."""
    return room_config.resolve_room(dev_id, device_store.get_cached_room(dev_id))


def _mark_device_offline(device_id: str) -> None:
    """Set online state to offline and force usage gauges to zero."""
    ONLINE.labels(**_metric_labels(device_id)).set(0)
    POWER.labels(**_metric_labels(device_id)).set(0)
    CURRENT.labels(**_metric_labels(device_id)).set(0)
    VOLTAGE.labels(**_metric_labels(device_id)).set(float("nan"))
    SWITCH.labels(**_metric_labels(device_id)).set(float("nan"))


def _poll_device(dev: dict) -> dict:
    """Poll a single device locally and return a status dict."""
    dev_id = dev.get("id", "")
    name = dev.get("name", "unknown")
    room = _resolve_room(dev_id)
    version = dev.get("version") or "3.3"
    local_key = dev.get("local_key") or dev.get("key")
    ip = dev.get("ip") or dev.get("last_ip")

    dps = None
    source = "—"

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

    # Some offline devices return a non-empty status with all-null values.
    if dps and all(v is None for v in dps.values()):
        dps = None

    if not dps:
        _mark_device_offline(dev_id)
        track_outage(dev_id, name, is_online=False)
        return {
            "id": dev_id,
            "name": name,
            "room": room,
            "online": False,
            "source": source,
        }

    ONLINE.labels(**_metric_labels(dev_id)).set(1)

    # Normalize numeric DPS codes (e.g. Zebronics ZEB-SP116 uses 1,20,22,25)
    # to standard string codes expected by the rest of the code.
    _norm = {}
    numeric_map = {"1": "switch_1", "20": "cur_voltage", "22": "cur_current", "25": "cur_power"}
    for k, v in dps.items():
        sk = str(k)
        if sk in numeric_map and numeric_map[sk] not in dps:
            _norm[numeric_map[sk]] = v
    dps = {**_norm, **dps}

    # Use key-in-dict check so a literal False value is not skipped by `or`.
    switch_state: bool | None = None
    for code in ("switch_1", "switch", "led_switch"):
        if code in dps:
            switch_state = bool(dps[code])
            break

    raw_power = dps.get("cur_power") or dps.get("Power")
    power_value = None
    if raw_power is not None:
        try:
            power_value = float(raw_power) / 10
        except (ValueError, TypeError):
            power_value = None
    if power_value is not None:
        POWER.labels(**_metric_labels(dev_id)).set(power_value)
    elif switch_state is False:
        POWER.labels(**_metric_labels(dev_id)).set(0)
    else:
        POWER.labels(**_metric_labels(dev_id)).set(float("nan"))

    raw_current = dps.get("cur_current") or dps.get("Current")
    current_value = None
    if raw_current is not None:
        try:
            current_value = float(raw_current) / 1000
        except (ValueError, TypeError):
            current_value = None
    if current_value is not None:
        CURRENT.labels(**_metric_labels(dev_id)).set(current_value)
    elif switch_state is False:
        CURRENT.labels(**_metric_labels(dev_id)).set(0)
    else:
        CURRENT.labels(**_metric_labels(dev_id)).set(float("nan"))

    raw_voltage = dps.get("cur_voltage") or dps.get("Voltage")
    voltage_value = None
    if raw_voltage is not None:
        try:
            voltage_value = float(raw_voltage) / 10
        except (ValueError, TypeError):
            voltage_value = None
    if voltage_value is not None:
        VOLTAGE.labels(**_metric_labels(dev_id)).set(voltage_value)
    else:
        VOLTAGE.labels(**_metric_labels(dev_id)).set(float("nan"))

    raw_energy = _extract_power_dps(dps).get("energy")
    _update_energy(dev_id, raw_energy)

    if switch_state is True:
        SWITCH.labels(**_metric_labels(dev_id)).set(1)
    elif switch_state is False:
        SWITCH.labels(**_metric_labels(dev_id)).set(0)
    else:
        SWITCH.labels(**_metric_labels(dev_id)).set(float("nan"))

    power_dps = _extract_power_dps(dps)
    outage_event = track_outage(dev_id, name, is_online=True)

    result = {
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
    if outage_event:
        result["event"] = outage_event
    return result


def _update_energy(device_id: str, raw: float | None) -> None:
    if raw is None:
        return
    try:
        current = float(raw) / 10
    except (ValueError, TypeError):
        return
    if current < 0:
        return

    _energy_tracker.update(device_id, current)


def _poll_all():
    from . import webhook

    devices = device_store.get_devices()
    for dev in devices:
        dev_id = dev.get("id", "")
        try:
            status = _poll_device(dev)
        except Exception:
            log.error("Poll failed", device=dev.get("name"), exc_info=True)
            status = {
                "id": dev_id,
                "name": dev.get("name", "unknown"),
                "room": _resolve_room(dev_id),
                "online": False,
                "source": "—",
            }
        device_store.set_status(status)

    statuses = device_store.get_statuses()
    if statuses:
        stats = webhook.push_webhooks(statuses)
        if stats["sent"] > 0 or stats["failed"] > 0:
            log.info("Webhook delivery", sent=stats["sent"], failed=stats["failed"])


def _polling_loop():
    log.info("Starting metrics polling loop", interval_seconds=POLL_INTERVAL)
    while True:
        try:
            _poll_all()
        except Exception:
            log.error("Polling loop error", exc_info=True)
        time.sleep(POLL_INTERVAL)


_polling_thread = None
if os.getenv("TUYA_DISABLE_POLL_THREAD", "").lower() not in ("1", "true", "yes"):
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
    devices = []
    rooms = set()
    for dev in device_store.get_devices():
        dev_id = dev.get("id", "")
        room = _resolve_room(dev_id)
        rooms.add(room)
        devices.append(
            {
                "id": dev_id,
                "name": dev.get("name", "unknown"),
                "room": room,
                "created_at": dev.get("created_at"),
                "updated_at": dev.get("updated_at"),
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
    """Return cached device statuses as JSON for async dashboard updates.

    This serves the last values polled by the background thread.
    It does NOT block on fresh API calls.
    """
    return jsonify(device_store.get_statuses())


@flask_app.route("/status/<device_id>")
def status_single(device_id):
    """Return cached status for a single device."""
    status = device_store.get_status(device_id)
    if status:
        return jsonify(status)
    return jsonify({"error": "Device not found or not yet polled"}), 404


@flask_app.route("/refresh", methods=["POST"])
def refresh():
    global _last_refresh_error
    try:
        devices = _discover_devices()
        _last_refresh_error = None
        log.info("Manual device refresh", count=len(devices))
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"success": True, "count": len(devices)})
        return redirect(url_for("index"))
    except Exception as exc:
        _last_refresh_error = str(exc)
        log.error("Manual device refresh failed", error=str(exc), exc_info=True)
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"success": False, "error": str(exc)}), 503
        return Response(str(exc), status=503, mimetype="text/plain")


def _try_toggle(device_id: str, state: bool) -> None:
    """Toggle a device on/off locally via tinytuya (no cloud API)."""
    dev = None
    for d in device_store.get_devices():
        if d.get("id") == device_id:
            dev = d
            break

    if not dev:
        raise RuntimeError(f"Device {device_id} not found in store")

    local_key = dev.get("local_key") or dev.get("key")
    ip = dev.get("ip") or dev.get("last_ip")
    version = dev.get("version") or "3.3"

    if not local_key or not ip:
        raise RuntimeError(f"Device {device_id} missing local_key or IP")

    # Try string codes first, then numeric code 1 (common on many plugs)
    switch_codes = ["switch_1", "switch", "led_switch", 1]

    last_error = None
    for code in switch_codes:
        try:
            local_client.toggle_device_local(
                device_id, local_key, ip, state, version, switch_code=code
            )
            log.info(
                "Toggled device locally",
                device_id=device_id,
                state=state,
                code=code,
            )
            return
        except Exception as exc:
            last_error = exc
            log.warning(
                "Local toggle attempt failed",
                device_id=device_id,
                code=code,
                error=str(exc),
            )

    raise last_error or RuntimeError("All local toggle attempts failed")


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
    """Return cached status for a single device."""
    status = device_store.get_status(device_id)
    if status:
        return jsonify(status)
    return jsonify({"error": "Device not found or not yet polled"}), 404


@flask_app.route("/rooms")
def rooms_page():
    """Room assignment management page."""
    devices_with_rooms = []
    for dev in device_store.get_devices():
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


@flask_app.route("/api/state")
def api_state():
    """Return exporter state including the last manual refresh error."""
    return jsonify(
        {
            "last_refresh_error": _last_refresh_error,
            "device_count": len(device_store.get_devices()),
            "status_count": len(device_store.get_statuses()),
        }
    )


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

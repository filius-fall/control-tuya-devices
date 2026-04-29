"""Prometheus metrics exporter for Tuya devices.

Usage with gunicorn:
    gunicorn -w 1 -b 0.0.0.0:8000 tuya.metrics_exporter:app

The background polling thread runs in the worker process and updates
metrics that are served via the WSGI app.
"""

import threading
import time
import os

from prometheus_client import Gauge, Counter, make_wsgi_app
from prometheus_client.registry import CollectorRegistry

from . import logger
from . import devices as device_config
from .main import _collect_device_reading

log = logger.logs

POLL_INTERVAL = int(os.getenv("TUYA_POLL_INTERVAL", "30"))

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

# Counter so increase() handles resets correctly (e.g. midnight)
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

# Track previous raw add_ele reading per device to compute deltas
_prev_energy: dict[str, float] = {}


def _update_energy(device_name: str, raw: float | None) -> None:
    """Update the energy counter, handling midnight resets.

    Tuya devices report add_ele in 0.1 kWh units. We convert to kWh
    and use a Counter so Prometheus increase() handles resets.
    """
    if raw is None:
        return
    try:
        current = float(raw) / 10  # convert to kWh
    except (ValueError, TypeError):
        return

    prev = _prev_energy.get(device_name)
    if prev is None:
        # First reading — we don't know the delta, so just record the baseline
        _prev_energy[device_name] = current
        return

    if current >= prev:
        delta = current - prev
    else:
        # Midnight reset: the device rolled over to 0 (or close to it)
        delta = current

    if delta > 0:
        ENERGY.labels(device=device_name).inc(delta)
        _prev_energy[device_name] = current


def _poll_all():
    """Poll all devices and update Prometheus metrics."""
    switches = device_config.load_switches()
    if not switches:
        log.warning("No switches configured, skipping poll")
        return

    for sw in switches:
        name = sw.get("name", "unknown")
        reading = _collect_device_reading(sw)
        if not reading:
            ONLINE.labels(device=name).set(0)
            continue

        dps = reading.get("dps", {})
        source = reading.get("source", "unknown")

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


def _polling_loop():
    """Background thread that polls devices continuously."""
    log.info("Starting metrics polling loop", interval_seconds=POLL_INTERVAL)
    while True:
        try:
            _poll_all()
        except Exception:
            log.error("Polling loop error", exc_info=True)
        time.sleep(POLL_INTERVAL)


_polling_thread = threading.Thread(target=_polling_loop, daemon=True)
_polling_thread.start()

app = make_wsgi_app(registry=REGISTRY)

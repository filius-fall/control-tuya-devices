import json
import os
import time
from datetime import datetime, timezone

from . import logger
from . import api_client
from . import devices as device_config

log = logger.logs

DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "readings.jsonl")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _append_reading(reading: dict):
    """Append a single reading as a JSON line (JSONL format)."""
    _ensure_data_dir()
    with open(DATA_FILE, "a") as f:
        f.write(json.dumps(reading) + "\n")


def _collect_device_reading(device: dict) -> dict | None:
    """Fetch status for one device and return a flattened reading dict."""
    device_id = device.get("id")
    name = device.get("name", "unknown")
    if not device_id:
        return None

    status = api_client.get_device_status(device_id)
    if not status or not isinstance(status, dict):
        return None

    result = status.get("result", [])
    # result may be a list of {code, value} dicts
    dps = {}
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and "code" in item:
                dps[item["code"]] = item.get("value")
    elif isinstance(result, dict):
        dps = result

    reading = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "device_id": device_id,
        "device_name": name,
        "dps": dps,
    }
    return reading


def run_once():
    """Single-pass data collection for all configured switches."""
    switches = device_config.load_switches()
    if not switches:
        log.error("No switches configured. Add them to switches.toml or run discovery.")
        return

    log.info("Starting collection run", switch_count=len(switches))
    for sw in switches:
        reading = _collect_device_reading(sw)
        if reading:
            _append_reading(reading)
            log.info("Collected reading", device=sw.get("name"), dps=reading["dps"])
        else:
            log.warning("No reading for device", device=sw.get("name"))


def run_loop(interval_seconds: int = 30):
    """Continuous data collection loop."""
    log.info("Starting monitoring loop", interval_seconds=interval_seconds)
    try:
        while True:
            run_once()
            log.info("Sleeping until next collection", interval_seconds=interval_seconds)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        log.info("Monitoring loop stopped by user")


def discover():
    """List all devices visible in the Tuya Cloud and print them."""
    cloud_devices = api_client.get_devices()
    print(f"\nFound {len(cloud_devices)} device(s) in Tuya Cloud:\n")
    for dev in cloud_devices:
        print(f"  - Name: {dev.get('name', 'N/A')}")
        print(f"    ID:   {dev.get('id')}")
        print(f"    Key:  {dev.get('key', 'N/A')}")
        print()
    return cloud_devices


def main():
    """Entry point — runs a single collection pass by default."""
    run_once()


if __name__ == "__main__":
    main()

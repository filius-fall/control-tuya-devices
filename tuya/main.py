import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from . import logger
from . import api_client
from . import local_client
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
    """Fetch status for one device and return a flattened reading dict.

    Tries local control first (if local_key + ip are configured).
    Falls back to cloud polling otherwise.
    """
    device_id = device.get("id")
    name = device.get("name", "unknown")
    if not device_id:
        return None

    dps = None
    source = None

    # Try local control first — this is the most reliable way to get power DPs
    local_key = device.get("local_key")
    ip = device.get("ip")
    version = device.get("version", "3.3")
    if local_key and ip:
        local_status = local_client.get_device_status_local(
            device_id, local_key, ip, version
        )
        if local_status and "dps" in local_status:
            dps = local_status["dps"]
            source = "local"

    # Fall back to cloud polling
    if dps is None:
        cloud_status = api_client.get_device_status(device_id)
        if cloud_status and isinstance(cloud_status, dict):
            result = cloud_status.get("result", [])
            if isinstance(result, list):
                dps = {
                    item["code"]: item.get("value")
                    for item in result
                    if isinstance(item, dict) and "code" in item
                }
            elif isinstance(result, dict):
                dps = result
            source = "cloud"

    if dps is None:
        log.warning("No reading for device", device=name, device_id=device_id)
        return None

    reading = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "device_id": device_id,
        "device_name": name,
        "source": source,
        "dps": dps,
    }
    return reading


def run_once():
    """Single-pass data collection for all configured switches."""
    switches = device_config.load_switches()
    if not switches:
        log.error(
            "No switches configured. Add them to switches.toml or run --discover."
        )
        return

    log.info("Starting collection run", switch_count=len(switches))
    for sw in switches:
        reading = _collect_device_reading(sw)
        if reading:
            _append_reading(reading)
            log.info(
                "Collected reading",
                device=sw.get("name"),
                source=reading["source"],
                dps=reading["dps"],
            )


def run_loop(interval_seconds: int = 30):
    """Continuous data collection loop."""
    log.info("Starting monitoring loop", interval_seconds=interval_seconds)
    try:
        while True:
            run_once()
            log.info(
                "Sleeping until next collection", interval_seconds=interval_seconds
            )
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        log.info("Monitoring loop stopped by user")


def discover():
    """List all devices visible in the Tuya Cloud and print them."""
    cloud_devices = api_client.get_devices()
    print(f"\nFound {len(cloud_devices)} device(s) in Tuya Cloud:\n")
    for dev in cloud_devices:
        print(f"  - Name:    {dev.get('name', 'N/A')}")
        print(f"    ID:      {dev.get('id')}")
        print(f"    Key:     {dev.get('key', 'N/A')}")
        print(f"    IP:      {dev.get('ip', 'N/A')}")
        print(f"    Version: {dev.get('version', 'N/A')}")
        print()
    return cloud_devices


# ---------------------------------------------------------------------------
# JSON-array persistence helpers (upstream compatibility)
# ---------------------------------------------------------------------------


def read_json_array(file_path):
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return []

    with open(file_path, "r", encoding="utf-8") as file:
        try:
            data = json.load(file)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {file_path}") from exc

    if not isinstance(data, list):
        raise ValueError(f"Expected {file_path} to contain a JSON array")

    return data


def append_json_array(file_path, item):
    data = read_json_array(file_path)
    data.append(item)

    temp_path = f"{file_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
        file.write("\n")

    os.replace(temp_path, file_path)
    return data


def main():
    """Entry point — runs a single collection pass by default."""
    run_once()


if __name__ == "__main__":
    main()

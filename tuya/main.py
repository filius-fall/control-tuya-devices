import json
import os
from datetime import datetime, timezone

from . import logger
from . import local_client

log = logger.logs


def _collect_device_reading(device: dict) -> dict | None:
    """Fetch status for one device locally and return a flattened reading dict."""
    device_id = device.get("id")
    name = device.get("name", "unknown")
    if not device_id:
        return None

    dps = None
    source = None

    local_key = device.get("local_key") or device.get("key")
    ip = device.get("ip") or device.get("last_ip")
    version = device.get("version", "3.3")
    if local_key and ip:
        local_status = local_client.get_device_status_local(
            device_id, ip_address=ip, local_key=local_key, version=version
        )
        if local_status and "dps" in local_status:
            dps = local_status["dps"]
            source = "local"

    if dps is None:
        log.warning("No local reading for device", device=name, device_id=device_id)
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
    """Single-pass data collection for all configured switches (prints JSONL)."""
    from . import devices as device_config

    switches = device_config.load_switches()
    if not switches:
        log.error(
            "No devices configured. Run 'tuya setup' to refresh the SQLite cache."
        )
        return

    log.info("Starting collection run", switch_count=len(switches))
    for sw in switches:
        reading = _collect_device_reading(sw)
        if reading:
            print(json.dumps(reading))
            log.info(
                "Collected reading",
                device=sw.get("name"),
                source=reading["source"],
                dps=reading["dps"],
            )


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

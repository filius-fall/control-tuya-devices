import json
import os
from datetime import datetime, timezone

from . import logger
from . import api_client
from . import local_client

log = logger.logs


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
    """Single-pass data collection for all configured switches (prints JSONL)."""
    from . import devices as device_config

    switches = device_config.load_switches()
    if not switches:
        log.error(
            "No switches configured. Add them to switches.toml or run 'tuya setup'."
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

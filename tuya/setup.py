"""Refresh device metadata in SQLite from Tuya Cloud and optional LAN scan."""

import tinytuya

from . import api_client
from . import device_store
from . import logger

log = logger.logs


def scan_local_network(timeout: float = 3.0) -> dict[str, dict]:
    """Scan the LAN for Tuya devices and return a map of device_id -> scan info."""
    log.info("Scanning local network for Tuya devices", timeout=timeout)
    try:
        found = tinytuya.deviceScan(verbose=False)
        by_id = {}
        for _, info in found.items():
            if isinstance(info, dict) and "id" in info:
                by_id[info["id"]] = info
            elif isinstance(info, dict) and "device_id" in info:
                by_id[info["device_id"]] = info
        log.info("Local scan complete", found=len(by_id))
        return by_id
    except Exception as exc:
        log.warning("Local scan failed", error=str(exc))
        return {}


def refresh_devices(scan: bool = True) -> list[dict]:
    """Fetch devices from cloud, enrich with LAN scan results, and persist to DB."""
    cloud_devices = api_client.get_devices()
    room_map = api_client.get_device_room_map()
    local = scan_local_network() if scan else {}

    merged = []
    for dev in cloud_devices:
        item = dict(dev)
        dev_id = item.get("id", "")
        if dev_id in local:
            item["ip"] = local[dev_id].get("ip", item.get("ip", ""))
            item["last_ip"] = local[dev_id].get("ip", item.get("last_ip", ""))
            item["version"] = local[dev_id].get("version", item.get("version", "3.3"))
        merged.append(item)

    device_store.upsert_devices(merged, room_map)
    log.info("Refreshed devices into database", count=len(merged), scanned=bool(scan))
    return device_store.get_devices()

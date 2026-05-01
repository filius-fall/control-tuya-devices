from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional

import tinytuya

from . import logger
from .models import (
    DeviceConfig,
    DeviceStatus,
    DpsMeta,
    PollResult,
    PowerReading,
)


DEVICES_FILE: str = os.path.join("data", "devices.json")
READINGS_DIR: str = os.path.join("data", "readings")
STATUS_FILE: str = os.path.join("data", "device_status.json")


def load_devices(path: str = DEVICES_FILE) -> List[DeviceConfig]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No devices file found at {path}. Run 'setup' first to fetch device details from the cloud."
        )
    with open(path, "r", encoding="utf-8") as f:
        raw: List[Dict[str, Any]] = json.load(f)
    return [DeviceConfig.from_dict(d) for d in raw]


def _load_device_status() -> Dict[str, DeviceStatus]:
    if not os.path.exists(STATUS_FILE):
        return {}
    with open(STATUS_FILE, "r", encoding="utf-8") as f:
        try:
            raw: Dict[str, Dict[str, Any]] = json.load(f)
            return {k: DeviceStatus.from_dict(v) for k, v in raw.items()}
        except json.JSONDecodeError:
            return {}


def _save_device_status(status: Dict[str, DeviceStatus]) -> None:
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    temp: str = f"{STATUS_FILE}.tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump({k: v.to_dict() for k, v in status.items()}, f, indent=2)
        f.write("\n")
    os.replace(temp, STATUS_FILE)


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")


def _parse_ts(ts_string: Optional[str]) -> datetime:
    if not ts_string:
        return datetime.now()
    return datetime.strptime(ts_string, "%Y-%m-%dT%H:%M:%S%z")


def _format_duration(seconds: float) -> str:
    s: int = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    hours: int = s // 3600
    mins: int = (s % 3600) // 60
    return f"{hours}h {mins}m {s % 60}s"


def poll_device(
    dev_id: str,
    ip_address: str,
    local_key: str,
    version: str = "3.3",
    retries: int = 2,
) -> Optional[Dict[str, Any]]:
    versions_to_try: List[str] = [version]
    for v in ("3.3", "3.4", "3.5", "3.1"):
        if v not in versions_to_try:
            versions_to_try.append(v)

    for attempt in range(retries):
        for v in versions_to_try:
            device: tinytuya.Device = tinytuya.Device(dev_id, ip_address, local_key)
            device.set_version(float(v))
            device.set_socketTimeout(5)
            try:
                status: Dict[str, Any] = device.status()
                if status and status.get("dps"):
                    return status
                if status and status.get("Error") and attempt < retries - 1:
                    continue
                return status
            except Exception:
                continue
    return None


def extract_power_dps(
    dps: Dict[str, Any],
    dps_mapping: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Any]:
    if not dps:
        return {}
    readings: Dict[str, Any] = {}

    dp_id_to_code: Dict[str, str] = {}
    if dps_mapping:
        for dp_id_str, meta in dps_mapping.items():
            dp_id_to_code[dp_id_str] = meta.get("code", dp_id_str)

    for dp_id_str, value in dps.items():
        code: str = dp_id_to_code.get(dp_id_str, dp_id_str)
        if code == "cur_voltage" and isinstance(value, (int, float)):
            readings["voltage_v"] = round(value / 10.0, 1)
        elif code == "cur_current" and isinstance(value, (int, float)):
            readings["current_ma"] = value
        elif code == "cur_power" and isinstance(value, (int, float)):
            readings["power_w"] = round(value / 10.0, 1)
        elif code == "add_ele" and isinstance(value, (int, float)):
            readings["energy_wh"] = round(value / 1000.0, 3)
        else:
            readings[code] = value

    return readings


def save_reading(
    reading: PowerReading,
    directory: str = READINGS_DIR,
) -> str:
    os.makedirs(directory, exist_ok=True)
    safe_name: str = reading.device_name.replace(" ", "_").replace("/", "_")
    file_path: str = os.path.join(directory, f"{safe_name}.jsonl")

    entry: Dict[str, Any] = {
        "timestamp": reading.timestamp,
        "data": reading.to_dict(),
    }

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return file_path


def _save_event(
    device_name: str,
    event: Dict[str, Any],
    directory: str = READINGS_DIR,
) -> str:
    os.makedirs(directory, exist_ok=True)
    safe_name: str = device_name.replace(" ", "_").replace("/", "_")
    file_path: str = os.path.join(directory, f"{safe_name}.jsonl")
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    return file_path


def _build_reading(
    device: DeviceConfig,
    online: bool,
    dps: Optional[Dict[str, Any]] = None,
    dps_mapping: Optional[Dict[str, Dict[str, str]]] = None,
) -> PowerReading:
    now: str = _now_iso()
    decoded: Dict[str, Any] = extract_power_dps(dps or {}, dps_mapping) if online else {}

    return PowerReading(
        timestamp=now,
        device_name=device.name,
        device_id=device.id,
        ip=device.ip_address,
        online=online,
        voltage_v=decoded.get("voltage_v"),
        current_ma=decoded.get("current_ma"),
        power_w=decoded.get("power_w"),
        energy_wh=decoded.get("energy_wh"),
        extra={k: v for k, v in decoded.items() if k not in ("voltage_v", "current_ma", "power_w", "energy_wh")},
    )


def poll_devices(
    devices: Optional[List[DeviceConfig]] = None,
    save: bool = True,
) -> List[PollResult]:
    if devices is None:
        devices = load_devices()

    device_status: Dict[str, DeviceStatus] = _load_device_status()
    now: str = _now_iso()
    results: List[PollResult] = []

    for dev in devices:
        if not all([dev.id, dev.ip_address, dev.local_key]):
            logger.logs.warning("Skipping device with missing fields", device=dev.name)
            continue

        logger.logs.info("Polling device", device=dev.name, ip=dev.ip_address)
        status: Optional[Dict[str, Any]] = poll_device(
            dev.id, dev.ip_address, dev.local_key, dev.version
        )

        prev: DeviceStatus = device_status.get(dev.id, DeviceStatus())
        was_online: Optional[bool] = prev.online
        event: Optional[Dict[str, Any]] = None

        if status:
            dps: Dict[str, Any] = status.get("dps", {})
            reading: PowerReading = _build_reading(dev, online=True, dps=dps, dps_mapping=dev.dps_mapping)

            if save:
                save_reading(reading)

            logger.logs.info("Saved reading", device=dev.name, data_points=len(reading.to_dict()))

            if was_online is False:
                outage_secs: Optional[float] = None
                if prev.last_offline:
                    outage_secs = (_parse_ts(now) - _parse_ts(prev.last_offline)).total_seconds()

                event = {
                    "timestamp": now,
                    "data": {
                        "event": "power_restored",
                        "device_name": dev.name,
                        "device_id": dev.id,
                        "ip": dev.ip_address,
                        "offline_since": prev.last_offline,
                        "outage_duration_seconds": outage_secs,
                    },
                }
                if save:
                    _save_event(dev.name, event)
                duration_str: str = f" (was offline for {_format_duration(outage_secs)})" if outage_secs else ""
                print(f"  POWER RESTORED: {dev.name}{duration_str}")

            device_status[dev.id] = DeviceStatus(online=True, last_online=now, last_offline=prev.last_offline)
            results.append(PollResult(reading=reading, event=event))
        else:
            reading = _build_reading(dev, online=False)
            if save:
                save_reading(reading)

            if was_online is True or was_online is None:
                event = {
                    "timestamp": now,
                    "data": {
                        "event": "power_lost",
                        "device_name": dev.name,
                        "device_id": dev.id,
                        "ip": dev.ip_address,
                        "last_seen_online": prev.last_online,
                    },
                }
                if save:
                    _save_event(dev.name, event)
                print(f"  POWER LOST: {dev.name} (last seen: {prev.last_online or 'never'})")

            device_status[dev.id] = DeviceStatus(online=False, last_online=prev.last_online, last_offline=now)
            results.append(PollResult(reading=reading, event=event))

    _save_device_status(device_status)
    return results


def stream_readings(
    interval_seconds: int = 60,
    devices: Optional[List[DeviceConfig]] = None,
    save: bool = True,
) -> Generator[List[PollResult], None, None]:
    if devices is None:
        devices = load_devices()

    while True:
        try:
            results: List[PollResult] = poll_devices(devices, save=save)
            yield results
        except KeyboardInterrupt:
            break
        except Exception as exc:
            logger.logs.error("Polling cycle failed", error=str(exc))
            yield []

        time.sleep(interval_seconds)


def poll_continuously(
    interval_seconds: int = 60,
    devices: Optional[List[DeviceConfig]] = None,
) -> None:
    if devices is None:
        devices = load_devices()

    logger.logs.info("Starting continuous polling", devices=len(devices), interval=interval_seconds)
    print(f"  Polling {len(devices)} device(s) every {interval_seconds}s. Press Ctrl+C to stop.\n")

    for _ in stream_readings(interval_seconds=interval_seconds, devices=devices):
        pass

    print("\n  Polling stopped.")


def poll_all_once(
    devices: Optional[List[DeviceConfig]] = None,
) -> List[PollResult]:
    return poll_devices(devices, save=True)


def cmd_list() -> None:
    devices: List[DeviceConfig] = load_devices()
    print(f"\n{'Name':<25} {'IP':<16} {'ID':<22} {'Model'}")
    print("-" * 80)
    for dev in devices:
        print(f"{dev.name[:24]:<25} {dev.ip_address:<16} {dev.id:<22} {dev.model}")
    print(f"\n{len(devices)} device(s) found in {DEVICES_FILE}")


def refresh_devices() -> List[DeviceConfig]:
    from . import api_client

    print("Refreshing device data from cloud + local scan...")

    devices_raw: List[Dict[str, Any]] = api_client.get_device_details()
    if not devices_raw:
        print("No devices found on cloud. Is your app account linked?")
        return []

    print("Scanning local network...")
    scan_results: Optional[Dict[str, Any]] = tinytuya.deviceScan(verbose=False, poll=False)

    ip_map: Dict[str, Dict[str, str]] = {}
    if scan_results:
        for ip, info in scan_results.items():
            gw_id: str = info.get("gwId", "")
            if gw_id:
                ip_map[gw_id] = {"ip": ip, "version": str(info.get("version", "3.3"))}

    cloud: tinytuya.Cloud = api_client.create_tuya_client()
    updated: List[DeviceConfig] = []

    for dev in devices_raw:
        dev_id: str = dev.get("id", "")
        scan_info: Dict[str, str] = ip_map.get(dev_id, {})

        dps_mapping: Dict[str, DpsMeta] = {}
        try:
            dps_result = cloud.getdps(dev_id)
            if dps_result and dps_result.get("result"):
                for item in dps_result["result"].get("status", []):
                    dp_id = str(item.get("dp_id", ""))
                    dps_mapping[dp_id] = {
                        "code": item.get("code", ""),
                        "type": item.get("type", ""),
                        "values": item.get("values", ""),
                    }
        except Exception as exc:
            logger.logs.warning("Could not fetch DPS mapping", device_id=dev_id, error=str(exc))

        entry: DeviceConfig = DeviceConfig(
            id=dev_id,
            name=dev.get("name", dev_id),
            local_key=dev.get("local_key", dev.get("key", "")),
            ip_address=scan_info.get("ip", ""),
            version=scan_info.get("version", str(dev.get("version", "3.3"))),
            model=dev.get("model", ""),
            product_name=dev.get("product_name", ""),
            category=dev.get("category", ""),
            mac=dev.get("mac", ""),
            dps_mapping=dps_mapping,
        )
        updated.append(entry)
        ip_str = entry.ip_address or "no IP"
        print(f"  ✓ {entry.name} → {ip_str} (key: {entry.local_key[:4]}...)")

    with open(DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump([d.to_dict() for d in updated], f, indent=2)
        f.write("\n")

    print(f"\nRefreshed {len(updated)} device(s). Saved to {DEVICES_FILE}")
    return updated


def scan_devices() -> List[DeviceConfig]:
    print("Scanning local network for Tuya devices (no cloud API needed)...")
    print()

    scan_results: Optional[Dict[str, Any]] = tinytuya.deviceScan(verbose=False, poll=False)

    devices: List[DeviceConfig] = load_devices()
    updated: bool = False

    ip_map: Dict[str, Dict[str, str]] = {}
    if scan_results:
        for ip, info in scan_results.items():
            gw_id: str = info.get("gwId", "")
            if gw_id:
                ip_map[gw_id] = {"ip": ip, "version": str(info.get("version", "3.3"))}

    for dev in devices:
        scan_info: Dict[str, str] = ip_map.get(dev.id, {})
        new_ip: str = scan_info.get("ip", "")
        new_ver: str = scan_info.get("version", dev.version)

        if new_ip and new_ip != dev.ip_address:
            print(f"  {dev.name}: {dev.ip_address} → {new_ip} (IP updated)")
            dev.ip_address = new_ip
            dev.version = new_ver
            updated = True
        elif new_ip:
            print(f"  {dev.name}: {new_ip} (unchanged)")
        else:
            print(f"  {dev.name}: not found on network (offline?)")

    if updated:
        with open(DEVICES_FILE, "w", encoding="utf-8") as f:
            json.dump([d.to_dict() for d in devices], f, indent=2)
            f.write("\n")
        print(f"\nUpdated IPs saved to {DEVICES_FILE}")
    else:
        print("\nNo IP changes detected.")

    return devices

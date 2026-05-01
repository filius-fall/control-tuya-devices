import time
import json
import os

import tinytuya

from . import logger


DEVICES_FILE = os.path.join("data", "devices.json")
READINGS_DIR = os.path.join("data", "readings")


def cmd_list():
    devices = load_devices()
    print(f"\n{'Name':<25} {'IP':<16} {'ID':<22} {'Model'}")
    print("-" * 80)
    for dev in devices:
        name = dev.get("name", "?")[:24]
        ip = dev.get("ip_address", "?")
        dev_id = dev.get("id", "?")
        model = dev.get("model", "?")
        print(f"{name:<25} {ip:<16} {dev_id:<22} {model}")
    print(f"\n{len(devices)} device(s) found in {DEVICES_FILE}")


def load_devices(path=DEVICES_FILE):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No devices file found at {path}. Run 'setup' first to fetch device details from the cloud."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def poll_device(dev_id, ip_address, local_key, version="3.3"):
    device = tinytuya.Device(dev_id, ip_address, local_key)
    device.set_version(float(version))
    device.set_socketTimeout(5)
    try:
        status = device.status()
        return status
    except Exception as exc:
        logs = logger.logs.bind(device_id=dev_id, error=str(exc))
        logs.error("Failed to poll device locally")
        return None


def extract_power_dps(dps, dps_mapping=None):
    if not dps:
        return {}
    readings = {}

    dp_id_to_code = {}
    if dps_mapping:
        for dp_id_str, meta in dps_mapping.items():
            dp_id_to_code[dp_id_str] = meta.get("code", dp_id_str)

    for dp_id_str, value in dps.items():
        code = dp_id_to_code.get(dp_id_str, dp_id_str)
        if code in ("cur_voltage",) and isinstance(value, (int, float)):
            readings["voltage_v"] = round(value / 10.0, 1)
        elif code in ("cur_current",) and isinstance(value, (int, float)):
            readings["current_ma"] = value
        elif code in ("cur_power",) and isinstance(value, (int, float)):
            readings["power_w"] = round(value / 10.0, 1)
        elif code in ("add_ele",) and isinstance(value, (int, float)):
            readings["energy_wh"] = round(value / 1000.0, 3)
        else:
            readings[code] = value

    return readings


def save_reading(device_name, reading, directory=READINGS_DIR):
    os.makedirs(directory, exist_ok=True)
    safe_name = device_name.replace(" ", "_").replace("/", "_")
    file_path = os.path.join(directory, f"{safe_name}.jsonl")

    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "data": reading,
    }

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return file_path


def poll_all_once(devices=None):
    if devices is None:
        devices = load_devices()

    results = []
    for dev in devices:
        dev_id = dev.get("id", dev.get("dev_id", ""))
        ip = dev.get("ip_address", dev.get("ip", ""))
        local_key = dev.get("local_key", dev.get("key", ""))
        name = dev.get("name", dev_id)
        version = str(dev.get("version", "3.3"))

        if not all([dev_id, ip, local_key]):
            logger.logs.warning(
                "Skipping device with missing fields", device=name
            )
            continue

        logger.logs.info("Polling device", device=name, ip=ip)
        status = poll_device(dev_id, ip, local_key, version)

        if status:
            dps = status.get("dps", {})
            dps_mapping = dev.get("dps_mapping")
            readings = extract_power_dps(dps, dps_mapping)
            readings["device_name"] = name
            readings["device_id"] = dev_id
            readings["ip"] = ip

            saved_to = save_reading(name, readings)
            logger.logs.info(
                "Saved reading",
                device=name,
                file=saved_to,
                data_points=len(readings),
            )
            results.append(readings)
        else:
            logger.logs.warning("No response from device", device=name)

    return results


def poll_continuously(interval_seconds=60, devices=None):
    if devices is None:
        devices = load_devices()

    logger.logs.info(
        "Starting continuous polling",
        devices=len(devices),
        interval=interval_seconds,
    )

    while True:
        try:
            poll_all_once(devices)
        except KeyboardInterrupt:
            logger.logs.info("Polling stopped by user")
            break
        except Exception as exc:
            logger.logs.error("Polling cycle failed", error=str(exc))

        time.sleep(interval_seconds)

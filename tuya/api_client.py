import threading

import tinytuya

from . import config
from . import logger

log = logger.logs

_client_lock = threading.RLock()
_cloud_client = None


def create_tuya_client(force_refresh: bool = False):
    """Return a cached authenticated tinytuya Cloud client."""
    global _cloud_client
    with _client_lock:
        if _cloud_client is not None and not force_refresh:
            return _cloud_client

        settings = config.require_tuya_settings()
        client = tinytuya.Cloud(
            apiRegion=settings["api_region"],
            apiKey=settings["api_key"],
            apiSecret=settings["api_secret"],
        )
        if client.error:
            raise RuntimeError(f"Tuya Cloud authentication failed: {client.error}")
        _cloud_client = client
        return _cloud_client


def invalidate_tuya_client() -> None:
    global _cloud_client
    with _client_lock:
        _cloud_client = None


def get_cloud_client():
    """Alias for create_tuya_client for backward compatibility."""
    return create_tuya_client()


def _with_client_call(func, *args, **kwargs):
    last_error = None
    for attempt in range(2):
        client = create_tuya_client(force_refresh=(attempt == 1))
        try:
            return func(client, *args, **kwargs)
        except Exception as exc:
            last_error = exc
            log.warning("Tuya cloud call failed", error=str(exc), retry=attempt == 0)
            invalidate_tuya_client()
    if last_error:
        raise last_error
    raise RuntimeError("Tuya cloud call failed")


def _error_text(payload) -> str:
    if isinstance(payload, dict):
        msg = payload.get("msg") or payload.get("Msg") or payload.get("Error")
        code = payload.get("code")
        if msg and code is not None:
            return f"{msg} (code {code})"
        if msg:
            return str(msg)
    return str(payload)


def get_devices():
    """Return a list of all devices from the Tuya Cloud, including online status."""

    def _call(client):
        return client.getdevices(verbose=True)

    raw = _with_client_call(_call)
    if isinstance(raw, dict) and ("Error" in raw or raw.get("success") is False):
        raise RuntimeError(f"Failed to fetch devices: {_error_text(raw)}")
    if not isinstance(raw, dict) or "result" not in raw:
        raise RuntimeError(f"Unexpected device list format: {_error_text(raw)}")

    devices = raw["result"]
    if not isinstance(devices, list):
        raise RuntimeError("Unexpected device list format")

    result = []
    for dev in devices:
        if not isinstance(dev, dict) or "id" not in dev:
            continue
        item = {
            "id": dev["id"],
            "name": dev.get("name", "").strip(),
            "online": dev.get("online"),
            "key": dev.get("local_key", ""),
            "mac": dev.get("mac", ""),
        }
        for k in (
            "category",
            "product_name",
            "product_id",
            "biz_type",
            "model",
            "sub",
            "icon",
            "version",
            "last_ip",
            "uuid",
            "node_id",
            "sn",
            "gateway_id",
            "uid",
            "home_id",
            "room_id",
        ):
            if k in dev:
                item[k] = dev[k]
        result.append(item)

    log.info("Fetched device list", count=len(result))
    return result


def get_device_details(client=None):
    """Backward-compatible alias used by upstream tests."""
    tuya_client = client or create_tuya_client()
    devices = tuya_client.getdevices()
    if isinstance(devices, dict) and (
        "Error" in devices or devices.get("success") is False
    ):
        raise RuntimeError(f"Failed to fetch Tuya devices: {_error_text(devices)}")
    log.info("Fetched Tuya devices", devices=devices)
    return devices


def getDeviceDetails(client=None):
    return get_device_details(client)


def get_device_status(device_id: str):
    """Return the current status (DPs) for a single device."""

    def _call(client):
        return client.getstatus(device_id)

    status = _with_client_call(_call)
    if isinstance(status, dict) and ("Error" in status or status.get("success") is False):
        log.warning("Failed to fetch status", device_id=device_id, error=_error_text(status))
        return None
    log.info("Fetched device status", device_id=device_id)
    return status


def get_device_metadata(device_id: str) -> dict | None:
    """Return one device metadata row from the Tuya Cloud device list."""
    for dev in get_devices():
        if dev.get("id") == device_id:
            return dev
    return None


def get_device_properties(device_id: str):
    """Return the properties/specification for a single device."""

    def _call(client):
        return client.getproperties(device_id)

    props = _with_client_call(_call)
    if isinstance(props, dict) and (
        "Error" in props or props.get("success") is False
    ):
        log.warning(
            "Failed to fetch properties",
            device_id=device_id,
            error=_error_text(props),
        )
        return None
    return props


def send_device_command(device_id: str, commands: list[dict]) -> dict:
    """Send a command to a device via the Tuya Cloud API."""

    def _call(client):
        payload = {"commands": commands}
        return client.sendcommand(deviceid=device_id, commands=payload)

    result = _with_client_call(_call)
    if isinstance(result, dict) and "Error" in result:
        raise RuntimeError(f"Command failed: {result}")
    if isinstance(result, dict) and not result.get("success", True):
        raise RuntimeError(f"Command failed: {result}")
    log.info(
        "Sent command to device", device_id=device_id, commands=commands, result=result
    )
    return result


def get_device_room_map() -> dict[str, str]:
    """Return a mapping of device_id -> room_name."""

    client = create_tuya_client()

    try:
        raw = client.getdevices(verbose=True)
    except Exception:
        log.error("Failed to fetch raw devices for room mapping", exc_info=True)
        invalidate_tuya_client()
        return {}

    if isinstance(raw, dict) and ("Error" in raw or raw.get("success") is False):
        log.warning(
            "Error fetching devices for room mapping", error=_error_text(raw)
        )
        return {}

    if not isinstance(raw, dict) or "result" not in raw:
        log.warning(
            "Unexpected device list format for room mapping", error=_error_text(raw)
        )
        return {}

    home_ids: set[str] = set()
    device_room_ids: dict[str, str] = {}

    for dev in raw["result"]:
        dev_id = dev.get("id")
        home_id = dev.get("home_id")
        room_id = dev.get("room_id")
        if home_id:
            home_ids.add(str(home_id))
        if dev_id and room_id is not None:
            device_room_ids[str(dev_id)] = str(room_id)

    if not home_ids:
        log.warning("No home_ids found in device data")
        return {}

    room_names: dict[str, str] = {}
    for home_id in home_ids:
        try:
            resp = client.cloudrequest(f"/v1.0/homes/{home_id}/rooms")
            if not isinstance(resp, dict) or not resp.get("success"):
                resp = client.cloudrequest(f"/v1.0/families/{home_id}/rooms")
        except Exception:
            log.warning("Failed to fetch rooms", home_id=home_id, exc_info=True)
            invalidate_tuya_client()
            continue

        if isinstance(resp, dict) and resp.get("success"):
            for room in resp.get("result", []):
                rid = str(room.get("room_id") or room.get("id"))
                room_names[rid] = room.get("name", "Unknown")
        else:
            log.warning("Failed to fetch rooms", home_id=home_id, response=resp)

    device_rooms = {
        dev_id: room_names.get(room_id, room_id)
        for dev_id, room_id in device_room_ids.items()
    }

    log.info("Mapped devices to rooms", count=len(device_rooms), homes=len(home_ids))
    return device_rooms

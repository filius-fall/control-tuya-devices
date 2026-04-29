import tinytuya

from . import config
from . import logger

log = logger.logs


def create_tuya_client():
    """Return an authenticated tinytuya Cloud client."""
    settings = config.require_tuya_settings()
    client = tinytuya.Cloud(
        apiRegion=settings["api_region"],
        apiKey=settings["api_key"],
        apiSecret=settings["api_secret"],
    )
    if client.error:
        raise RuntimeError(f"Tuya Cloud authentication failed: {client.error}")
    return client


def get_cloud_client():
    """Alias for create_tuya_client for backward compatibility."""
    return create_tuya_client()


def get_devices():
    """Return a list of all devices from the Tuya Cloud, including online status."""
    client = create_tuya_client()
    raw = client.getdevices(verbose=True)
    if isinstance(raw, dict) and "Error" in raw:
        raise RuntimeError(f"Failed to fetch devices: {raw}")
    if not isinstance(raw, dict) or "result" not in raw:
        raise RuntimeError("Unexpected device list format")

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
    log.info("Fetched Tuya devices", devices=devices)
    return devices


def getDeviceDetails(client=None):
    return get_device_details(client)


def get_device_status(device_id: str):
    """Return the current status (DPs) for a single device."""
    client = create_tuya_client()
    status = client.getstatus(device_id)
    if isinstance(status, dict) and "Error" in status:
        log.warning("Failed to fetch status", device_id=device_id, error=status)
        return None
    log.info("Fetched device status", device_id=device_id)
    return status


def get_device_properties(device_id: str):
    """Return the properties/specification for a single device."""
    client = create_tuya_client()
    props = client.getproperties(device_id)
    if isinstance(props, dict) and "Error" in props:
        log.warning("Failed to fetch properties", device_id=device_id, error=props)
        return None
    return props


def send_device_command(device_id: str, commands: list[dict]) -> dict:
    """Send a command to a device via the Tuya Cloud API.

    commands should be a list of dicts like:
        [{"code": "switch_1", "value": True}]
    """
    client = create_tuya_client()
    result = client.sendcommand(deviceid=device_id, commands=commands)
    if isinstance(result, dict) and "Error" in result:
        raise RuntimeError(f"Command failed: {result}")
    log.info("Sent command to device", device_id=device_id, commands=commands)
    return result


def get_device_room_map() -> dict[str, str]:
    """Return a mapping of device_id -> room_name.

    Extracts home_id and room_id from the raw device list, then fetches
    room names via the Tuya home-management API.
    """
    client = create_tuya_client()

    # Get raw device list to extract home_id/room_id
    try:
        raw = client.getdevices(verbose=True)
    except Exception:
        log.error("Failed to fetch raw devices for room mapping", exc_info=True)
        return {}

    if isinstance(raw, dict) and "Error" in raw:
        log.warning("Error fetching devices for room mapping", error=raw)
        return {}

    if not isinstance(raw, dict) or "result" not in raw:
        log.warning("Unexpected device list format for room mapping")
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

    # Fetch room names for each home
    room_names: dict[str, str] = {}
    for home_id in home_ids:
        resp = client.cloudrequest(f"/v1.0/homes/{home_id}/rooms")
        if not isinstance(resp, dict) or not resp.get("success"):
            resp = client.cloudrequest(f"/v1.0/families/{home_id}/rooms")

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

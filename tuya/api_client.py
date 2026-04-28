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
    """Return a list of all devices from the Tuya Cloud."""
    client = create_tuya_client()
    devices = client.getdevices()
    if isinstance(devices, dict) and "Error" in devices:
        raise RuntimeError(f"Failed to fetch devices: {devices}")
    log.info(
        "Fetched device list", count=len(devices) if isinstance(devices, list) else 0
    )
    return devices


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

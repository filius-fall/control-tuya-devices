import tinytuya
from . import config
from . import logger

log = logger.logs


def get_cloud_client():
    """Return an authenticated tinytuya Cloud client."""
    if not config.CLIENT_KEY or not config.CLIENT_SECRET or not config.API_REGION:
        raise RuntimeError(
            "Missing Tuya API credentials. Set CLIENTKEY, CLIENTSECRET, and APIREGION in your .env file."
        )

    client = tinytuya.Cloud(
        apiRegion=config.API_REGION,
        apiKey=config.CLIENT_KEY,
        apiSecret=config.CLIENT_SECRET,
    )
    if client.error:
        raise RuntimeError(f"Tuya Cloud authentication failed: {client.error}")
    return client


def get_devices():
    """Return a list of all devices from the Tuya Cloud."""
    client = get_cloud_client()
    devices = client.getdevices()
    if isinstance(devices, dict) and "Error" in devices:
        raise RuntimeError(f"Failed to fetch devices: {devices}")
    log.info("Fetched device list", count=len(devices) if isinstance(devices, list) else 0)
    return devices


def get_device_status(device_id: str):
    """Return the current status (DPs) for a single device."""
    client = get_cloud_client()
    status = client.getstatus(device_id)
    if isinstance(status, dict) and "Error" in status:
        log.warning("Failed to fetch status", device_id=device_id, error=status)
        return None
    log.info("Fetched device status", device_id=device_id)
    return status


def get_device_properties(device_id: str):
    """Return the properties/specification for a single device."""
    client = get_cloud_client()
    props = client.getproperties(device_id)
    if isinstance(props, dict) and "Error" in props:
        log.warning("Failed to fetch properties", device_id=device_id, error=props)
        return None
    return props

import tinytuya

from . import config
from . import logger


def create_tuya_client():
    settings = config.require_tuya_settings()
    return tinytuya.Cloud(
        apiRegion=settings["api_region"],
        apiKey=settings["api_key"],
        apiSecret=settings["api_secret"],
    )


def get_device_details(client=None):
    tuya_client = client or create_tuya_client()
    devices = tuya_client.getdevices()
    logger.logs.info("Fetched Tuya devices", devices=devices)
    return devices


def getDeviceDetails(client=None):
    return get_device_details(client)

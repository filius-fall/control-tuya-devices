from typing import Any, Dict, List, Optional

import tinytuya

from . import config
from . import logger
from .models import TuyaCredentials


def create_tuya_client(
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    api_region: Optional[str] = None,
) -> tinytuya.Cloud:
    if api_key and api_secret and api_region:
        settings: TuyaCredentials = {
            "api_key": api_key,
            "api_secret": api_secret,
            "api_region": api_region,
        }
    else:
        settings = config.require_tuya_settings()
    return tinytuya.Cloud(
        apiRegion=settings["api_region"],
        apiKey=settings["api_key"],
        apiSecret=settings["api_secret"],
    )


def get_device_details(client: Optional[tinytuya.Cloud] = None) -> List[Dict[str, Any]]:
    tuya_client = client or create_tuya_client()
    devices: List[Dict[str, Any]] = tuya_client.getdevices()
    logger.logs.info("Fetched Tuya devices", devices=devices)
    return devices

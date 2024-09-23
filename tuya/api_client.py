import tinytuya
from . import config
from . import logger

API_KEY = config.CLIENTKEY
API_SECRET=config.CLIENTSECRET
APIREGION=config.APIREGION

tuya_client = tinytuya.Cloud(
    apiRegion=APIREGION,
    apiKey=API_KEY,
    apiSecret=API_SECRET
)

file_path = 'devices.json'

def getDeviceDetails():
    devices = tuya_client.getdevices()
    logger.logs.info("This is info",devices=devices)
    return devices

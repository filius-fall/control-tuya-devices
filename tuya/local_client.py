import tinytuya
from . import logger

log = logger.logs


def get_device_status_local(device_id: str, local_key: str, ip_address: str, version: str = "3.3") -> dict | None:
    """Poll a Tuya device directly over the local network.

    This usually returns ALL DPs including cur_power, cur_current, cur_voltage,
    which the Cloud API often omits.
    """
    try:
        d = tinytuya.Device(device_id, ip_address, local_key)
        d.set_version(float(version))
        d.set_socketPersistent(False)
        d.set_socketTimeout(5)

        payload = d.generate_payload(tinytuya.DP_QUERY)
        d.send(payload)
        data = d.receive()

        if data and "dps" in data:
            log.info("Local poll succeeded", device_id=device_id, ip=ip_address)
            return {"dps": data["dps"]}
        else:
            log.warning("Local poll returned no DPs", device_id=device_id, ip=ip_address, response=data)
            return None
    except Exception as exc:
        log.warning("Local poll failed", device_id=device_id, ip=ip_address, error=str(exc))
        return None

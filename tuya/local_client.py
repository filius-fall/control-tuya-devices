import tinytuya
from . import logger

log = logger.logs


def get_device_status_local(
    device_id: str, local_key: str, ip_address: str, version: str = "3.3"
) -> dict | None:
    """Poll a Tuya device directly over the local network.

    Tries multiple protocol versions on failure for robustness.
    Returns {"dps": {...}} on success, None on failure.
    """
    versions_to_try = [version]
    for v in ("3.3", "3.4", "3.5", "3.1"):
        if v not in versions_to_try:
            versions_to_try.append(v)

    for v in versions_to_try:
        try:
            d = tinytuya.Device(device_id, ip_address, local_key)
            d.set_version(float(v))
            d.set_socketPersistent(False)
            d.set_socketTimeout(5)

            payload = d.generate_payload(tinytuya.DP_QUERY)
            d.send(payload)
            data = d.receive()

            if data and "dps" in data:
                log.info(
                    "Local poll succeeded",
                    device_id=device_id,
                    ip=ip_address,
                    version=v,
                )
                return {"dps": data["dps"]}
        except Exception as exc:
            log.debug(
                "Local poll attempt failed",
                device_id=device_id,
                ip=ip_address,
                version=v,
                error=str(exc),
            )
            continue

    log.warning(
        "Local poll failed after all version attempts",
        device_id=device_id,
        ip=ip_address,
    )
    return None

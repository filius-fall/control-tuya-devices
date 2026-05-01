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

            # Try device.status() first — returns full DPS on many devices
            data = d.status()
            if data and "dps" in data:
                log.info(
                    "Local poll succeeded (status)",
                    device_id=device_id,
                    ip=ip_address,
                    version=v,
                )
                return {"dps": data["dps"]}

            # Fallback to manual DP_QUERY payload
            payload = d.generate_payload(tinytuya.DP_QUERY)
            d.send(payload)
            data = d.receive()

            if data and "dps" in data:
                log.info(
                    "Local poll succeeded (dp_query)",
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


def toggle_device_local(
    device_id: str,
    local_key: str,
    ip_address: str,
    state: bool,
    version: str = "3.3",
    switch_code: str = "switch_1",
) -> bool:
    """Toggle a device on/off locally via tinytuya.

    Returns True on success, raises on failure.
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

            # Support both string codes ("switch_1") and numeric codes (1)
            code_key = switch_code if isinstance(switch_code, int) else switch_code
            payload = d.generate_payload(
                tinytuya.CONTROL, {code_key: state}
            )
            d.send(payload)
            data = d.receive()

            if data:
                log.info(
                    "Local toggle succeeded",
                    device_id=device_id,
                    ip=ip_address,
                    version=v,
                    state=state,
                    switch_code=switch_code,
                )
                return True
        except Exception as exc:
            log.debug(
                "Local toggle attempt failed",
                device_id=device_id,
                ip=ip_address,
                version=v,
                error=str(exc),
            )
            continue

    raise RuntimeError(
        f"Local toggle failed for {device_id} after all version attempts"
    )

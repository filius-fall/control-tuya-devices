"""Auto-configure switches.toml by fetching device metadata from Tuya Cloud.

Optionally scans the local network to fill in IP addresses automatically.
"""

import tinytuya
from . import api_client
from . import logger

log = logger.logs


def scan_local_network(timeout: float = 3.0) -> dict[str, dict]:
    """Scan the LAN for Tuya devices and return a map of device_id -> scan info.

    Returns a dict keyed by device id with keys: ip, version, productKey, etc.
    """
    log.info("Scanning local network for Tuya devices", timeout=timeout)
    try:
        found = tinytuya.deviceScan(verbose=False, scantime=timeout)
        # tinytuya.deviceScan returns a dict keyed by IP or name depending on version.
        # Normalise to a dict keyed by device id.
        by_id = {}
        for key, info in found.items():
            if isinstance(info, dict) and "id" in info:
                by_id[info["id"]] = info
            elif isinstance(info, dict) and "device_id" in info:
                by_id[info["device_id"]] = info
        log.info("Local scan complete", found=len(by_id))
        return by_id
    except Exception as exc:
        log.warning("Local scan failed", error=str(exc))
        return {}


def build_switches_toml(scan: bool = True) -> str:
    """Fetch cloud devices and generate a switches.toml string.

    If *scan* is True, also tries to discover local IPs.
    """
    cloud_devices = api_client.get_devices()
    local = scan_local_network() if scan else {}

    lines = [
        '# Tuya Smart Switch Configuration',
        '# Auto-generated from Tuya Cloud.',
        '# Local IPs were discovered via LAN scan where possible.',
        '# Update names and uncomment the switches you want to monitor.',
        '',
    ]

    for dev in cloud_devices:
        dev_id = dev.get("id", "")
        name = dev.get("name", "unknown")
        local_key = dev.get("key", "")
        version = dev.get("version", "3.3")
        ip = dev.get("ip", "")

        # Try to enrich from local scan if cloud didn't provide IP
        if not ip and dev_id in local:
            ip = local[dev_id].get("ip", "")
            version = local[dev_id].get("version", version)

        lines.append("# [[switch]]")
        lines.append(f'# id = "{dev_id}"')
        lines.append(f'# name = "{name}"')
        lines.append(f'# local_key = "{local_key}"')
        if ip:
            lines.append(f'# ip = "{ip}"')
        else:
            lines.append('# ip = "192.168.1.XXX"  # <-- fill this in')
        lines.append(f'# version = "{version}"')
        lines.append('')

    return "\n".join(lines) + "\n"


def write_switches_toml(path: str = "switches.toml", scan: bool = True) -> None:
    """Write auto-generated switches.toml to disk."""
    content = build_switches_toml(scan=scan)
    with open(path, "w") as f:
        f.write(content)
    log.info("Wrote auto-generated switch config", path=path)

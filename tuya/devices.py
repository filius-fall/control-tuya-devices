from . import device_store
from . import logger

log = logger.logs


def load_switches(path: str | None = None) -> list[dict]:
    """Load monitored devices from the shared SQLite database."""
    devices = device_store.get_devices()
    log.info("Loaded devices from database", count=len(devices))
    return devices

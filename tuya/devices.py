import tomllib
from pathlib import Path

from . import logger

log = logger.logs

DEFAULT_CONFIG_PATH = "switches.toml"


def load_switches(path: str = DEFAULT_CONFIG_PATH) -> list[dict]:
    """Load the switch configuration from a TOML file.

    Expected format:
    [[switch]]
    id = "bf1234567890abcdef1234"
    name = "Living Room Plug"
    local_key = "a1b2c3d4e5f6g7h8"
    ip = "192.168.1.45"
    version = "3.3"

    If local_key and ip are provided, the monitor will use local control
    (which reliably returns power DPs). Otherwise it falls back to cloud polling.
    """
    config_path = Path(path)
    if not config_path.exists():
        log.warning("Switch config file not found", path=str(config_path))
        return []

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    switches = data.get("switch", [])
    if isinstance(switches, dict):
        switches = [switches]
    log.info("Loaded switch config", path=str(config_path), count=len(switches))
    return switches


def save_example_config(path: str = DEFAULT_CONFIG_PATH):
    """Write an example switches.toml if one does not exist."""
    if Path(path).exists():
        return
    example = """# Tuya Smart Switch Configuration
# Add your switches here. You can get device IDs from the Tuya Developer Platform
# or by running: uv run python run.py --discover
#
# For LOCAL control (recommended for power monitoring), you need:
#   id        - from Tuya Cloud
#   local_key - from Tuya Cloud (shown as 'Device Token' or via getdevices())
#   ip        - local IP address of the device on your LAN
#   version   - protocol version, usually "3.3" (default)
#
# If you omit local_key and ip, the monitor will fall back to cloud polling,
# which often does NOT include cur_power / cur_current / cur_voltage.

[[switch]]
id = "bfXXXXXXXXXXXXXXXXXXXX"
name = "Living Room Plug"
local_key = "a1b2c3d4e5f6g7h8"
ip = "192.168.1.45"
version = "3.3"

# [[switch]]
# id = "bfYYYYYYYYYYYYYYYYYYYY"
# name = "Kitchen Plug"
# local_key = "z9y8x7w6v5u4t3s2"
# ip = "192.168.1.46"
"""
    with open(path, "w") as f:
        f.write(example)
    log.info("Created example switch config", path=path)

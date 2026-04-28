import tomllib
import os
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

    [[switch]]
    id = "bf0987654321fedcba0987"
    name = "Kitchen Plug"
    """
    config_path = Path(path)
    if not config_path.exists():
        log.warning("Switch config file not found", path=str(config_path))
        return []

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    switches = data.get("switch", [])
    if isinstance(switches, dict):
        # Single switch case — normalize to list
        switches = [switches]
    log.info("Loaded switch config", path=str(config_path), count=len(switches))
    return switches


def save_example_config(path: str = DEFAULT_CONFIG_PATH):
    """Write an example switches.toml if one does not exist."""
    if Path(path).exists():
        return
    example = '''# Tuya Smart Switch Configuration
# Add your switches here. You can get device IDs from the Tuya Developer Platform
# or by running: uv run python -m tuya.main --discover

[[switch]]
id = "bfXXXXXXXXXXXXXXXXXXXX"
name = "Living Room Plug"

# [[switch]]
# id = "bfYYYYYYYYYYYYYYYYYYYY"
# name = "Kitchen Plug"
'''
    with open(path, "w") as f:
        f.write(example)
    log.info("Created example switch config", path=path)

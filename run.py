"""Backward-compatible entry point — delegates to tuya.cli."""
from tuya.cli import cli

if __name__ == "__main__":
    cli()

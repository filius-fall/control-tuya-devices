from __future__ import annotations

import sys
from typing import List

from . import setup as setup_wizard
from .local import load_devices, poll_all_once, poll_continuously, cmd_list, stream_readings, refresh_devices, scan_devices
from .models import DeviceConfig, PollResult
from .serve import serve


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run python run.py <command> [options]")
        print()
        print("Commands:")
        print("  setup           Interactive setup wizard (needs internet, one-time)")
        print("  refresh         Re-fetch keys + IPs from cloud (needs internet)")
        print("  scan            Update device IPs via local scan (no internet needed)")
        print("  poll            Poll all devices once (local only)")
        print("  poll <seconds>  Poll all devices continuously at interval (local only)")
        print("  serve           Start always-on polling + webhook push service")
        print("  list            List saved devices")
        sys.exit(1)

    command: str = sys.argv[1].lower()

    if command == "setup":
        setup_wizard.run_setup()
    elif command == "refresh":
        refresh_devices()
    elif command == "scan":
        scan_devices()
    elif command == "poll":
        devices: List[DeviceConfig] = load_devices()
        print(f"Loaded {len(devices)} device(s) from local cache")

        interval: int | None = None
        if len(sys.argv) > 2:
            try:
                interval = int(sys.argv[2])
            except ValueError:
                print("Error: interval must be a number of seconds")
                sys.exit(1)

        if interval is not None:
            poll_continuously(interval_seconds=interval, devices=devices)
        else:
            results: List[PollResult] = poll_all_once(devices)
            online: int = sum(1 for r in results if r.reading.online)
            print(f"Polled {len(results)} device(s), {online} online")
    elif command == "serve":
        interval: int | None = None
        if len(sys.argv) > 2:
            try:
                interval = int(sys.argv[2])
            except ValueError:
                print("Error: interval must be a number of seconds")
                sys.exit(1)
        serve(interval_seconds=interval)
    elif command == "list":
        cmd_list()
    else:
        print(f"Unknown command: {command}")
        print("Use 'setup', 'refresh', 'scan', 'poll', 'serve', or 'list'")
        sys.exit(1)


if __name__ == "__main__":
    main()

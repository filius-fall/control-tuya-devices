import sys

from . import setup as setup_wizard
from . import local


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python run.py <command> [options]")
        print()
        print("Commands:")
        print("  setup           Interactive setup wizard (needs internet, one-time)")
        print("  poll            Poll all devices once (local only)")
        print("  poll <seconds>  Poll all devices continuously at interval (local only)")
        print("  list            List saved devices")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "setup":
        setup_wizard.run_setup()
    elif command == "poll":
        devices = local.load_devices()
        print(f"Loaded {len(devices)} device(s) from local cache")

        interval = None
        if len(sys.argv) > 2:
            try:
                interval = int(sys.argv[2])
            except ValueError:
                print("Error: interval must be a number of seconds")
                sys.exit(1)

        if interval is not None:
            local.poll_continuously(interval_seconds=interval, devices=devices)
        else:
            results = local.poll_all_once(devices)
            print(f"Polled {len(results)} device(s)")
    elif command == "list":
        local.cmd_list()
    else:
        print(f"Unknown command: {command}")
        print("Use 'setup', 'poll', or 'list'")
        sys.exit(1)


if __name__ == "__main__":
    main()

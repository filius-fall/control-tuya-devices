import argparse
from tuya.main import run_once, run_loop, discover
from tuya.devices import save_example_config


def cli():
    parser = argparse.ArgumentParser(description="Tuya Smart Switch Power Monitor")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="List all devices visible in the Tuya Cloud",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuous monitoring loop (default: single pass)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Polling interval in seconds when using --loop (default: 30)",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Create an example switches.toml if it does not exist",
    )
    args = parser.parse_args()

    if args.init_config:
        save_example_config()
        return

    if args.discover:
        discover()
        return

    if args.loop:
        run_loop(interval_seconds=args.interval)
    else:
        run_once()


if __name__ == "__main__":
    cli()

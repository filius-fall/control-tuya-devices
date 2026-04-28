import argparse
import sys

from tuya.main import run_once, run_loop
from tuya.devices import save_example_config
from tuya import setup as setup_module
from tuya import interactive_setup
from tuya import top as top_module
from tuya import history as history_module
from tuya import api_client
from tuya.rich_output import print_device_table, print_summary, print_error


def cmd_discover():
    """Discover and list all Tuya Cloud devices."""
    try:
        devices = api_client.get_devices()
        print(f"\nFound {len(devices)} device(s) in Tuya Cloud:\n")
        for dev in devices:
            print(f"  - Name:    {dev.get('name', 'N/A')}")
            print(f"    ID:      {dev.get('id')}")
            print(f"    Key:     {dev.get('key', 'N/A')}")
            print(f"    IP:      {dev.get('ip', 'N/A')}")
            print(f"    Version: {dev.get('version', 'N/A')}")
            print()
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)


def cmd_status():
    """Print a one-shot rich table of all configured switches."""
    from tuya import devices as device_config
    from tuya.main import _collect_device_reading

    switches = device_config.load_switches()
    if not switches:
        print_error("No switches configured. Run 'tuya init-config' or 'tuya setup'.")
        sys.exit(1)

    statuses = {}
    for sw in switches:
        dev_id = sw.get("id")
        reading = _collect_device_reading(sw)
        if reading:
            statuses[dev_id] = reading
        else:
            statuses[dev_id] = {"online": False, "dps": {}, "source": "—"}

    print_summary(switches, statuses)
    print_device_table(switches, statuses, title="Current Status")


def cmd_setup(args):
    """Auto-generate switches.toml from Tuya Cloud (and optional LAN scan)."""
    path = args.output or "switches.toml"
    try:
        if args.non_interactive:
            content = setup_module.build_switches_toml(scan=args.scan)
            with open(path, "w") as f:
                f.write(content)
            print(
                f"[green]Wrote {path}[/green] — edit it to uncomment the switches you want to monitor."
            )
        else:
            interactive_setup.run_interactive_setup(path=path, scan=args.scan)
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)


def cmd_history(args):
    """Show historic power data for a device."""
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()
    try:
        summary = history_module.summarize_power_logs(args.device_id, hours=args.hours)
        table = Table(
            title=f"Power History (last {args.hours}h)",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Metric")
        table.add_column("Value", justify="right")

        table.add_row("Readings", str(summary["count"]))
        table.add_row(
            "Avg Power",
            f"{summary['avg_power']:.2f} W" if summary["avg_power"] else "—",
        )
        table.add_row(
            "Max Power",
            f"{summary['max_power']:.2f} W" if summary["max_power"] else "—",
        )
        table.add_row(
            "Min Power",
            f"{summary['min_power']:.2f} W" if summary["min_power"] else "—",
        )

        console.print(table)

        if args.verbose and summary["readings"]:
            detail = Table(title="Recent Readings", box=box.SIMPLE)
            detail.add_column("Time", style="dim")
            detail.add_column("Power", justify="right")
            for ts, val in summary["readings"][-20:]:
                detail.add_row(str(ts), f"{val:.2f} W")
            console.print(detail)
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)


def cli():
    parser = argparse.ArgumentParser(description="Tuya Smart Switch Power Monitor")
    sub = parser.add_subparsers(dest="command", help="Commands")

    # discover
    sub.add_parser("discover", help="List all devices visible in the Tuya Cloud")

    # status
    sub.add_parser("status", help="Show a one-shot rich table of current device status")

    # top
    p_top = sub.add_parser("top", help="Live-updating top view (tuya-top)")
    p_top.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Refresh interval in seconds (default: 2)",
    )

    # loop
    p_loop = sub.add_parser("loop", help="Continuous monitoring loop (JSONL output)")
    p_loop.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Polling interval in seconds (default: 30)",
    )

    # setup
    p_setup = sub.add_parser(
        "setup", help="Auto-generate switches.toml from Tuya Cloud"
    )
    p_setup.add_argument("--output", default="switches.toml", help="Output path")
    p_setup.add_argument(
        "--no-scan",
        dest="scan",
        action="store_false",
        default=True,
        help="Skip LAN IP scan",
    )
    p_setup.add_argument(
        "--non-interactive",
        action="store_true",
        default=False,
        help="Write all devices commented-out instead of interactive selection",
    )

    # history
    p_hist = sub.add_parser("history", help="Show historic power data for a device")
    p_hist.add_argument("device_id", help="Device ID to query")
    p_hist.add_argument(
        "--hours", type=int, default=24, help="Hours of history (default: 24)"
    )
    p_hist.add_argument(
        "--verbose", action="store_true", help="Show individual readings"
    )

    # init-config
    sub.add_parser("init-config", help="Create an example switches.toml")

    args = parser.parse_args()

    if args.command == "discover":
        cmd_discover()
    elif args.command == "status":
        cmd_status()
    elif args.command == "top":
        top_module.run_top(interval=args.interval)
    elif args.command == "loop":
        run_loop(interval_seconds=args.interval)
    elif args.command == "setup":
        cmd_setup(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "init-config":
        save_example_config()
    else:
        # Default: show help
        parser.print_help()


def main():
    """Entry point for the 'tuya' console script."""
    cli()


if __name__ == "__main__":
    cli()

import argparse
import signal
import sys
import time

from rich.console import Console

from tuya import device_store
from tuya import setup as setup_module
from tuya import top as top_module
from tuya import history as history_module
from tuya.rich_output import print_device_table, print_summary, print_error

console = Console(force_terminal=True)


def cmd_status():
    """Print a one-shot rich table of all configured switches."""
    from tuya import devices as device_config
    from tuya.main import _collect_device_reading

    switches = device_config.load_switches()
    if not switches:
        print_error("No switches configured. Run 'tuya setup'.")
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
    """Refresh the SQLite device cache from Tuya Cloud and optional LAN scan."""
    try:
        devices = setup_module.refresh_devices(scan=args.scan)
        console.print(
            f"[green]Refreshed {len(devices)} devices into SQLite cache.[/green]"
        )
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)


def cmd_list_devices(args):
    """List cached devices, optionally refreshing from cloud first."""
    try:
        if args.refresh:
            devices = setup_module.refresh_devices(scan=args.scan)
        else:
            devices = device_store.get_devices()
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)

    if not devices:
        print_error("No devices configured. Run 'tuya setup' or 'tuya list-devices --refresh'.")
        sys.exit(1)

    from rich.table import Table
    from rich import box

    table = Table(
        title="Cached Devices",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Device", style="cyan")
    table.add_column("Device ID", style="dim")
    table.add_column("Room")
    table.add_column("IP")
    table.add_column("Version")
    table.add_column("Local Key", justify="center")

    for dev in devices:
        local_key = dev.get("local_key") or dev.get("key") or ""
        table.add_row(
            dev.get("name", "unknown"),
            dev.get("id", ""),
            dev.get("room") or "unknown",
            dev.get("ip") or dev.get("last_ip") or "—",
            str(dev.get("version") or "3.3"),
            "yes" if local_key else "no",
        )

    console.print(table)
    console.print(f"[dim]{len(devices)} device(s)[/dim]")


def cmd_history(args):
    """Show historic power data for a device."""
    from rich.table import Table
    from rich import box

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


def cmd_serve(args):
    """Run always-on polling service with webhook push (no Flask/gunicorn)."""
    import os
    from tuya import webhook
    from tuya.main import _collect_device_reading
    from tuya import devices as device_config
    from tuya.outage import track_outage

    interval = args.interval or int(os.getenv("TUYA_POLL_INTERVAL", "60"))

    def _signal_handler(signum, frame):
        console.print("\n[dim]Shutting down...[/dim]")
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    switches = device_config.load_switches()
    if not switches:
        print_error("No devices configured. Run 'tuya setup'.")
        sys.exit(1)

    webhook_urls = [u.strip() for u in os.getenv("WEBHOOK_URLS", "").split(",") if u.strip()]
    console.print("[cyan]Tuya Polling Service[/cyan]")
    console.print(f"  Devices:    {len(switches)}")
    console.print(f"  Interval:   {interval}s")
    console.print(f"  Webhooks:   {len(webhook_urls)}")
    for url in webhook_urls:
        console.print(f"    → {url}")
    console.print()
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")

    cycle = 0
    while True:
        cycle += 1
        try:
            statuses = []
            for sw in switches:
                dev_id = sw.get("id")
                name = sw.get("name", "unknown")
                reading = _collect_device_reading(sw)
                if reading:
                    status = {
                        "id": dev_id,
                        "name": name,
                        "online": True,
                        "source": reading.get("source", "local"),
                        "dps": reading.get("dps", {}),
                    }
                    outage_event = track_outage(dev_id, name, is_online=True)
                    if outage_event:
                        status["event"] = outage_event
                else:
                    status = {"id": dev_id, "name": name, "online": False, "source": "—"}
                    track_outage(dev_id, name, is_online=False)

                statuses.append(status)

            if webhook_urls and statuses:
                stats = webhook.push_webhooks(statuses)
                if stats["failed"] > 0:
                    console.print(
                        f"[dim][#{cycle}][/dim] [red]Webhooks: {stats['sent']} sent, {stats['failed']} failed[/red]"
                    )

            for s in statuses:
                online_str = "[green]online[/green]" if s["online"] else "[red]OFFLINE[/red]"
                console.print(
                    f"[dim][#{cycle}][/dim] {s['name']} {online_str}"
                )

        except KeyboardInterrupt:
            break
        except Exception as exc:
            console.print(f"[red]Poll cycle failed: {exc}[/red]")

        time.sleep(interval)


def cli():
    parser = argparse.ArgumentParser(description="Tuya Smart Switch Power Monitor")
    sub = parser.add_subparsers(dest="command", help="Commands")

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

    # setup
    p_setup = sub.add_parser(
        "setup", help="Refresh the SQLite device cache from Tuya Cloud"
    )
    p_setup.add_argument(
        "--no-scan",
        dest="scan",
        action="store_false",
        default=True,
        help="Skip LAN IP scan",
    )

    # list-devices
    p_list = sub.add_parser("list-devices", help="List cached devices")
    p_list.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh the SQLite cache from Tuya Cloud before listing",
    )
    p_list.add_argument(
        "--no-scan",
        dest="scan",
        action="store_false",
        default=True,
        help="Skip LAN IP scan when used with --refresh",
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

    # serve
    p_serve = sub.add_parser(
        "serve", help="Always-on polling service with webhook push"
    )
    p_serve.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Poll interval in seconds (default: TUYA_POLL_INTERVAL or 60)",
    )

    args = parser.parse_args()

    if args.command == "status":
        cmd_status()
    elif args.command == "top":
        top_module.run_top(interval=args.interval)
    elif args.command == "setup":
        cmd_setup(args)
    elif args.command == "list-devices":
        cmd_list_devices(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "serve":
        cmd_serve(args)
    else:
        # Default: show help
        parser.print_help()


def main():
    """Entry point for the 'tuya' console script."""
    cli()


if __name__ == "__main__":
    cli()

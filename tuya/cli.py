import argparse
import sys

from rich.console import Console

from tuya.main import run_once
from tuya.devices import save_example_config
from tuya import setup as setup_module
from tuya import textual_setup
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
    """Auto-generate switches.toml from Tuya Cloud (and optional LAN scan)."""
    path = args.output or "switches.toml"
    try:
        if args.non_interactive:
            content = setup_module.build_switches_toml(scan=args.scan)
            with open(path, "w") as f:
                f.write(content)
            console.print(f"[green]Wrote {path}[/green] with all devices enabled.")
        else:
            textual_setup.run_textual_setup(path=path, scan=args.scan)
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)


def cmd_metrics(args):
    """Start the Prometheus metrics exporter (via gunicorn)."""
    import subprocess

    port = args.port
    workers = args.workers
    console.print(f"[green]Starting Tuya Prometheus exporter[/green] on port {port}...")
    console.print(f"[dim]Poll interval: {args.interval}s  |  Workers: {workers}[/dim]")
    console.print(f"[dim]Metrics endpoint: http://localhost:{port}/metrics[/dim]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")

    try:
        subprocess.run(
            [
                "gunicorn",
                "-w",
                str(workers),
                "-b",
                f"0.0.0.0:{port}",
                "tuya.metrics_exporter:app",
            ],
            check=True,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Exporter stopped.[/yellow]")
    except FileNotFoundError:
        print_error("gunicorn not found. Run: uv pip install gunicorn")
        sys.exit(1)


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

    # metrics
    p_metrics = sub.add_parser(
        "metrics", help="Start Prometheus metrics exporter (gunicorn)"
    )
    p_metrics.add_argument(
        "--port", type=int, default=8000, help="HTTP port (default: 8000)"
    )
    p_metrics.add_argument(
        "--workers", type=int, default=1, help="Gunicorn workers (default: 1)"
    )
    p_metrics.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Device poll interval in seconds (default: 30)",
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
        help="Write all devices instead of interactive selection",
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

    args = parser.parse_args()

    if args.command == "status":
        cmd_status()
    elif args.command == "top":
        top_module.run_top(interval=args.interval)
    elif args.command == "metrics":
        cmd_metrics(args)
    elif args.command == "setup":
        cmd_setup(args)
    elif args.command == "history":
        cmd_history(args)
    else:
        # Default: show help
        parser.print_help()


def main():
    """Entry point for the 'tuya' console script."""
    cli()


if __name__ == "__main__":
    cli()

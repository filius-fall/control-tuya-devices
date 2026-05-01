import argparse
import signal
import subprocess
import sys
import time

from rich.console import Console

from tuya import device_store
from tuya import room_config
from tuya import setup as setup_module
from tuya import top as top_module
from tuya import history as history_module
from tuya import local_client
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


def _render_refresh_changes(changes: list[dict[str, str]]) -> None:
    if not changes:
        return

    updated = [c for c in changes if c["change"] == "updated"]
    inserted = [c for c in changes if c["change"] == "inserted"]
    unchanged = [c for c in changes if c["change"] == "unchanged"]

    if inserted:
        console.print(f"[green]{len(inserted)} inserted[/green]")
        for item in inserted:
            console.print(
                f"  [green]+[/green] {item['name']} [dim]({item['device_id']})[/dim]"
            )
    if updated:
        console.print(f"[yellow]{len(updated)} updated[/yellow]")
        for item in updated:
            console.print(
                f"  [yellow]~[/yellow] {item['name']} [dim]({item['device_id']})[/dim]"
            )
    if unchanged:
        console.print(f"[dim]{len(unchanged)} unchanged[/dim]")


def cmd_setup(args):
    """Refresh the SQLite device cache from Tuya Cloud and optional LAN scan."""
    try:
        devices, changes = setup_module.refresh_devices(scan=args.scan)
        console.print(
            f"[green]Refreshed {len(devices)} devices into SQLite cache.[/green]"
        )
        _render_refresh_changes(changes)
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)


def _fmt_local_time(value: str | None) -> str:
    if not value:
        return "—"
    try:
        from datetime import datetime

        return (
            datetime.fromisoformat(value)
            .astimezone()
            .strftime("%Y-%m-%d %H:%M:%S %Z")
        )
    except Exception:
        return str(value)


def cmd_list_devices(args):
    """List cached devices, optionally refreshing from cloud first."""
    changes_by_id = {}
    try:
        if args.refresh:
            devices, changes = setup_module.refresh_devices(scan=args.scan)
            changes_by_id = {c["device_id"]: c["change"] for c in changes}
            _render_refresh_changes(changes)
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
    table.add_column("Enabled")
    table.add_column("IP")
    table.add_column("Version")
    table.add_column("Local Key", justify="center")
    table.add_column("Added", style="dim")
    table.add_column("Updated", style="dim")

    room_overrides = room_config.get_overrides()
    for dev in devices:
        local_key = dev.get("local_key") or dev.get("key") or ""
        change = changes_by_id.get(dev.get("id", ""), "")
        row_style = "green" if change == "inserted" else ("yellow" if change == "updated" else "")
        dev_id = dev.get("id", "")
        room = room_overrides.get(dev_id) or dev.get("room") or "unknown"
        table.add_row(
            dev.get("name", "unknown"),
            dev_id,
            room,
            "yes" if dev.get("enabled") else "no",
            dev.get("ip") or dev.get("last_ip") or "—",
            str(dev.get("version") or "3.3"),
            "yes" if local_key else "no",
            _fmt_local_time(dev.get("created_at")),
            _fmt_local_time(dev.get("updated_at")),
            style=row_style,
        )

    console.print(table)
    console.print(f"[dim]{len(devices)} device(s)[/dim]")


def _ping_host(ip: str, timeout_seconds: int = 2) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout_seconds), ip],
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 2,
        )
        if proc.returncode == 0:
            return True, "ok"
        stderr = (proc.stderr or "").strip()
        return False, stderr or "no reply"
    except Exception as exc:
        return False, str(exc)


def cmd_doctor(args):
    """Check basic network reachability and local API health for cached devices."""
    devices = device_store.get_devices()
    if args.enabled_only:
        devices = [dev for dev in devices if dev.get("enabled")]

    if not devices:
        print_error("No cached devices to check.")
        sys.exit(1)

    from rich.table import Table
    from rich import box

    table = Table(
        title="Tuya Doctor",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Device", style="cyan")
    table.add_column("Enabled")
    table.add_column("IP")
    table.add_column("Ping")
    table.add_column("Local API")
    table.add_column("Notes", style="dim")

    ping_ok_count = 0
    local_ok_count = 0

    for dev in devices:
        dev_id = dev.get("id", "")
        name = dev.get("name", "unknown")
        enabled = bool(dev.get("enabled"))
        ip = dev.get("ip") or dev.get("last_ip") or ""
        local_key = dev.get("local_key") or dev.get("key") or ""
        version = str(dev.get("version") or "3.3")

        ping_text = "[yellow]skip[/yellow]"
        local_text = "[yellow]skip[/yellow]"
        notes: list[str] = []
        row_style = ""

        if not ip:
            notes.append("missing IP")
        else:
            ping_ok, ping_note = _ping_host(ip, timeout_seconds=args.ping_timeout)
            if ping_ok:
                ping_ok_count += 1
                ping_text = "[green]ok[/green]"
            else:
                ping_text = "[red]fail[/red]"
                notes.append(f"ping: {ping_note}")
                row_style = "red"

        if not local_key:
            notes.append("missing local key")
        elif not ip:
            pass
        else:
            status = local_client.get_device_status_local(dev_id, local_key, ip, version)
            if status and "dps" in status:
                local_ok_count += 1
                local_text = "[green]ok[/green]"
            else:
                local_text = "[red]fail[/red]"
                notes.append("local status failed")
                row_style = row_style or "yellow"

        table.add_row(
            name,
            "yes" if enabled else "no",
            ip or "—",
            ping_text,
            local_text,
            "; ".join(notes) if notes else "—",
            style=row_style,
        )

    console.print(table)
    console.print(
        f"[dim]Ping OK: {ping_ok_count}/{len(devices)} · Local API OK: {local_ok_count}/{len(devices)}[/dim]"
    )


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

    sub.add_parser("status", help="Show a one-shot rich table of current device status")

    p_top = sub.add_parser("top", help="Live-updating top view (tuya-top)")
    p_top.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Refresh interval in seconds (default: 2)",
    )

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

    p_doctor = sub.add_parser(
        "doctor", help="Check ping reachability and local API health for cached devices"
    )
    p_doctor.add_argument(
        "--enabled-only",
        action="store_true",
        help="Only check enabled devices",
    )
    p_doctor.add_argument(
        "--ping-timeout",
        type=int,
        default=2,
        help="Ping timeout in seconds (default: 2)",
    )

    p_hist = sub.add_parser("history", help="Show historic power data for a device")
    p_hist.add_argument("device_id", help="Device ID to query")
    p_hist.add_argument(
        "--hours", type=int, default=24, help="Hours of history (default: 24)"
    )
    p_hist.add_argument(
        "--verbose", action="store_true", help="Show individual readings"
    )

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
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "serve":
        cmd_serve(args)
    else:
        parser.print_help()


def main():
    """Entry point for the 'tuya' console script."""
    cli()


if __name__ == "__main__":
    cli()

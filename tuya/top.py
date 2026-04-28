"""Live-updating 'top' view for Tuya devices (like htop).

Usage:
    uv run tuya-top
"""

import time

from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich import box

from . import logger
from . import api_client
from . import local_client
from . import devices as device_config
from .rich_output import _extract_power_dps, _fmt_power, _fmt_current, _fmt_voltage

log = logger.logs

REFRESH_INTERVAL = 2.0


def _fetch_all_statuses(switches: list[dict]) -> dict[str, dict]:
    """Poll every switch and return a dict of device_id -> status info."""
    result = {}
    for sw in switches:
        dev_id = sw.get("id")
        if not dev_id:
            continue

        dps = None
        source = None
        online = False

        local_key = sw.get("local_key")
        ip = sw.get("ip")
        version = sw.get("version", "3.3")
        if local_key and ip:
            local_status = local_client.get_device_status_local(
                dev_id, local_key, ip, version
            )
            if local_status and "dps" in local_status:
                dps = local_status["dps"]
                source = "local"
                online = True

        if dps is None:
            cloud_status = api_client.get_device_status(dev_id)
            if cloud_status and isinstance(cloud_status, dict):
                online = True
                result_data = cloud_status.get("result", [])
                if isinstance(result_data, list):
                    dps = {
                        item["code"]: item.get("value")
                        for item in result_data
                        if isinstance(item, dict) and "code" in item
                    }
                elif isinstance(result_data, dict):
                    dps = result_data
                source = "cloud"
            else:
                online = False

        result[dev_id] = {
            "online": online,
            "dps": dps or {},
            "source": source or "—",
        }
    return result


def _make_table(switches: list[dict], statuses: dict[str, dict]) -> Table:
    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold magenta",
        expand=True,
    )
    table.add_column("Device", style="cyan", no_wrap=True, ratio=2)
    table.add_column("ID", style="dim", no_wrap=True, ratio=3)
    table.add_column("Status", justify="center", ratio=1)
    table.add_column("Power", justify="right", ratio=1)
    table.add_column("Current", justify="right", ratio=1)
    table.add_column("Voltage", justify="right", ratio=1)
    table.add_column("Source", justify="center", style="dim", ratio=1)

    total_power = 0.0
    online_count = 0

    for dev in switches:
        dev_id = dev.get("id", "N/A")
        name = dev.get("name", "unknown")
        st = statuses.get(dev_id, {})
        dps = st.get("dps", {})
        source = st.get("source", "—")
        is_online = st.get("online", False)

        if is_online:
            online_count += 1
            status_text = "[green]●[/green]"
        else:
            status_text = "[red]✗[/red]"

        p = _extract_power_dps(dps)
        power_str = _fmt_power(p.get("power"))
        current_str = _fmt_current(p.get("current"))
        voltage_str = _fmt_voltage(p.get("voltage"))

        # Accumulate rough total (only if we can parse a float)
        try:
            raw = p.get("power")
            if raw is not None:
                v = float(raw)
                if v > 10000:
                    v = v / 1000
                elif v > 1000:
                    v = v / 100
                total_power += v
        except (ValueError, TypeError):
            pass

        table.add_row(
            name, dev_id, status_text, power_str, current_str, voltage_str, source
        )

    return table, online_count, total_power


def _make_layout(table: Table, online: int, total: int, total_power: float) -> Layout:
    header_text = Text()
    header_text.append(f"Online: {online}/{total}  |  ")
    header_text.append(f"Total Draw: ~{total_power:.1f} W", style="bold yellow")
    header = Panel(header_text, border_style="blue", title="[bold]tuya-top[/bold]")

    body = Panel(table, border_style="dim")

    layout = Layout()
    layout.split_column(
        Layout(header, size=3),
        Layout(body),
    )
    return layout


def run_top(interval: float = REFRESH_INTERVAL) -> None:
    """Run the live updating top view."""
    switches = device_config.load_switches()
    if not switches:
        print(
            "[red]No switches configured.[/red] Run: uv run python run.py --init-config"
        )
        return

    with Live(refresh_per_second=1 / interval, screen=True) as live:
        try:
            while True:
                statuses = _fetch_all_statuses(switches)
                table, online, total_power = _make_table(switches, statuses)
                layout = _make_layout(table, online, len(switches), total_power)
                live.update(layout)
                time.sleep(interval)
        except KeyboardInterrupt:
            pass

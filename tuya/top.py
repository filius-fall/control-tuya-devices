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

from rich.console import Console

from . import logger
from . import api_client
from . import local_client
from . import devices as device_config
from .rich_output import (
    _extract_power_dps,
    _fmt_power,
    _fmt_current,
    _fmt_voltage,
    _fmt_energy,
)

log = logger.logs
console = Console(force_terminal=True)

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
    table.add_column("Online", justify="center", ratio=1)
    table.add_column("On", justify="center", ratio=1)
    table.add_column("Power", justify="right", ratio=1)
    table.add_column("Current", justify="right", ratio=1)
    table.add_column("Voltage", justify="right", ratio=1)
    table.add_column("Energy", justify="right", ratio=1)
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
            online_text = "[green]●[/green]"
        else:
            online_text = "[red]✗[/red]"

        p = _extract_power_dps(dps)
        switch_state = p.get("switch")
        if switch_state is True:
            on_text = "[bold green]ON[/bold green]"
        elif switch_state is False:
            on_text = "[dim]off[/dim]"
        else:
            on_text = "[yellow]?[/yellow]"

        power_str = _fmt_power(p.get("power"))
        current_str = _fmt_current(p.get("current"))
        voltage_str = _fmt_voltage(p.get("voltage"))
        energy_str = _fmt_energy(p.get("energy"))

        # Accumulate total power in watts
        try:
            raw = p.get("power")
            if raw is not None:
                total_power += float(raw) / 10
        except (ValueError, TypeError):
            pass

        table.add_row(
            name,
            online_text,
            on_text,
            power_str,
            current_str,
            voltage_str,
            energy_str,
            source,
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
        console.print("[red]No switches configured.[/red] Run: tuya setup")
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

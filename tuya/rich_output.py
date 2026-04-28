"""Rich console output for Tuya device status and tables."""

from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console(force_terminal=True)


def _fmt_power(val) -> str:
    """Format raw cur_power (Tuya reports in deciwatts, divide by 10 for watts)."""
    if val is None:
        return "—"
    try:
        return f"{float(val) / 10:.1f} W"
    except (ValueError, TypeError):
        return str(val)


def _fmt_voltage(val) -> str:
    """Format raw cur_voltage (Tuya reports in decivolts, divide by 10 for volts)."""
    if val is None:
        return "—"
    try:
        return f"{float(val) / 10:.1f} V"
    except (ValueError, TypeError):
        return str(val)


def _fmt_current(val) -> str:
    """Format raw cur_current (Tuya reports in milliamps, divide by 1000 for amps)."""
    if val is None:
        return "—"
    try:
        return f"{float(val) / 1000:.2f} A"
    except (ValueError, TypeError):
        return str(val)


def _extract_power_dps(dps: dict) -> dict:
    """Extract known power-related DPs from a status dict."""
    return {
        "power": dps.get("cur_power") or dps.get("Power"),
        "energy": dps.get("add_ele") or dps.get("total_power") or dps.get("elec_money"),
        "current": dps.get("cur_current") or dps.get("Current"),
        "voltage": dps.get("cur_voltage") or dps.get("Voltage"),
        "switch": dps.get("switch_1") or dps.get("switch") or dps.get("led_switch"),
    }


def _fmt_energy(val) -> str:
    """Format raw add_ele energy (Tuya reports in 0.1 kWh, divide by 10 for kWh)."""
    if val is None:
        return "—"
    try:
        return f"{float(val) / 10:.2f} kWh"
    except (ValueError, TypeError):
        return str(val)


def print_device_table(
    devices: list[dict], statuses: dict[str, dict], title: str = "Tuya Devices"
) -> None:
    """Print a rich table of devices with current status.

    *devices* is a list of device metadata dicts (from cloud or switches.toml).
    *statuses* is a dict mapping device_id -> status dict (cloud or local DPs).
    """
    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Device", style="cyan", no_wrap=True)
    table.add_column("Online", justify="center")
    table.add_column("On", justify="center")
    table.add_column("Power", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Voltage", justify="right")
    table.add_column("Energy", justify="right")
    table.add_column("Source", justify="center", style="dim")

    for dev in devices:
        dev_id = dev.get("id", "N/A")
        name = dev.get("name", "unknown")
        status_info = statuses.get(dev_id, {})
        dps = status_info.get("dps", {})
        source = status_info.get("source", "—")

        # Online/offline indicator
        is_online = status_info.get("online", dps.get("online", None))
        if is_online is True:
            online_text = "[green]●[/green]"
        elif is_online is False:
            online_text = "[red]✗[/red]"
        else:
            online_text = "[yellow]?[/yellow]"

        # On/off switch state
        power_dps = _extract_power_dps(dps)
        switch_state = power_dps.get("switch")
        if switch_state is True:
            on_text = "[bold green]ON[/bold green]"
        elif switch_state is False:
            on_text = "[dim]off[/dim]"
        else:
            on_text = "[yellow]?[/yellow]"

        power = _fmt_power(power_dps.get("power"))
        current = _fmt_current(power_dps.get("current"))
        voltage = _fmt_voltage(power_dps.get("voltage"))
        energy = _fmt_energy(power_dps.get("energy"))

        table.add_row(
            name, online_text, on_text, power, current, voltage, energy, source
        )

    console.print(table)


def print_summary(devices: list[dict], statuses: dict[str, dict]) -> None:
    """Print a quick summary panel with totals and timestamp."""
    total = len(devices)
    online = sum(
        1
        for dev in devices
        if statuses.get(dev.get("id", ""), {}).get("online", False) is True
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    text = Text()
    text.append(f"Devices: {total}  |  ")
    text.append(f"Online: {online}", style="green" if online == total else "yellow")
    text.append(
        f"  |  Offline: {total - online}",
        style="red" if (total - online) > 0 else "dim",
    )
    text.append(f"  |  {now}", style="dim")

    console.print(Panel(text, title="Tuya Monitor", border_style="blue"))


def print_error(message: str) -> None:
    console.print(f"[bold red]Error:[/bold red] {message}")

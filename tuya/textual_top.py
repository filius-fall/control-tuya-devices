"""Textual TUI for live-updating Tuya device monitoring (tuya-top)."""

import asyncio

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import DataTable, Static, Header, Footer, Sparkline

from . import local_client
from . import devices as device_config
from . import logger
from .rich_output import (
    _extract_power_dps,
    _fmt_power,
    _fmt_current,
    _fmt_voltage,
    _fmt_energy,
)

log = logger.logs

REFRESH_INTERVAL = 2.0


class TopApp(App):
    """Live device monitoring TUI with sparklines."""

    CSS = """
    Screen { align: center middle; }
    #main { width: 100%; height: 100%; padding: 0 1; }
    #header { height: auto; margin-bottom: 1; }
    #table { height: 1fr; border: solid blue; }
    #sparklines { height: auto; margin-top: 1; }
    .spark-container { width: 1fr; height: 10; border: solid green; padding: 1; }
    """

    def __init__(self, interval: float = REFRESH_INTERVAL, **kwargs):
        super().__init__(**kwargs)
        self.interval = interval
        self.switches: list[dict] = []
        self.history: dict[str, list[float]] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main"):
            yield Static("Loading...", id="header")
            yield DataTable(id="table")
            with Horizontal(id="sparklines"):
                # Sparklines will be added dynamically
                pass
        yield Footer()

    def on_mount(self) -> None:
        self.title = "tuya-top"
        self.sub_title = "Live Power Monitor"

        self.switches = device_config.load_switches()
        if not self.switches:
            self.notify(
                "No devices configured. Run 'tuya setup' first.", severity="error"
            )
            return

        table = self.query_one("#table", DataTable)
        table.add_columns(
            "Device", "Online", "On", "Power", "Current", "Voltage", "Energy", "Source"
        )
        table.zebra_stripes = True

        for sw in self.switches:
            dev_id = sw.get("id", "")
            self.history[dev_id] = []

        # Add sparkline widgets for each switch
        spark_container = self.query_one("#sparklines", Horizontal)
        for sw in self.switches:
            name = sw.get("name", "unknown")
            spark = Sparkline(
                data=[],
                summary_label=f"{name} Power (W)",
                classes="spark-container",
            )
            spark_container.mount(spark)

        self.set_interval(self.interval, self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        table = self.query_one("#table", DataTable)
        table.clear()

        total_power = 0.0
        online_count = 0

        spark_container = self.query_one("#sparklines", Horizontal)
        spark_idx = 0

        for sw in self.switches:
            dev_id = sw.get("id", "")
            name = sw.get("name", "unknown")
            dps, source, online = self._poll_device(sw)

            if online:
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

            # Track raw power for sparkline
            raw_power = self._parse_raw_power(p.get("power"))
            if raw_power is not None:
                self.history[dev_id].append(raw_power)
                if len(self.history[dev_id]) > 60:
                    self.history[dev_id].pop(0)
                total_power += raw_power

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

            # Update sparkline
            if spark_idx < len(spark_container.children):
                spark = spark_container.children[spark_idx]
                if isinstance(spark, Sparkline) and self.history[dev_id]:
                    spark.data = self.history[dev_id]
            spark_idx += 1

        header = self.query_one("#header", Static)
        header.update(
            f"Online: {online_count}/{len(self.switches)}  |  "
            f"Total Draw: ~{total_power:.1f} W"
        )

    def _poll_device(self, sw: dict) -> tuple[dict, str, bool]:
        dev_id = sw.get("id", "")
        local_key = sw.get("local_key") or sw.get("key")
        ip = sw.get("ip") or sw.get("last_ip")
        version = sw.get("version", "3.3")

        if local_key and ip:
            local_status = local_client.get_device_status_local(
                dev_id, local_key, ip, version
            )
            if local_status and "dps" in local_status:
                return local_status["dps"], "local", True

        return {}, "—", False

    @staticmethod
    def _parse_raw_power(val) -> float | None:
        """Convert raw cur_power (deciwatts) to watts."""
        if val is None:
            return None
        try:
            return float(val) / 10
        except (ValueError, TypeError):
            return None


def run_textual_top(interval: float = REFRESH_INTERVAL) -> None:
    app = TopApp(interval=interval)
    app.run()

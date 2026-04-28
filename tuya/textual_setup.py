"""Textual TUI for interactive Tuya device setup."""

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Input, SelectionList, Header, Footer, Static, Button
from textual.widgets.selection_list import Selection

from . import api_client
from . import devices as device_config
from . import setup as setup_module
from . import logger

log = logger.logs


class SetupApp(App):
    """Interactive device selection TUI with fuzzy filtering."""

    CSS = """
    Screen { align: center middle; }
    #container {
        width: 90;
        height: auto;
        max-height: 90%;
        border: solid $primary;
        padding: 1 2;
    }
    #search { margin-bottom: 1; }
    #selections { height: 25; border: solid $primary-darken-2; }
    #status { margin-top: 1; height: auto; color: $text-muted; }
    #buttons { margin-top: 1; align: center middle; }
    Button { margin: 0 2; }
    """

    BINDINGS = [
        ("enter", "done", "Done"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, path: str = "switches.toml", scan: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.path = path
        self.scan = scan
        self.cloud_devices: list[dict] = []
        self.existing_ids: set[str] = set()
        self.existing_ips: dict[str, str] = {}
        self._selected_ids: set[str] = set()
        self._rebuilding = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="container"):
            yield Static("Select devices to monitor", classes="title")
            yield Input(placeholder="Type to filter devices...", id="search")
            yield SelectionList(id="selections")
            yield Static("0 selected", id="status")
            with Horizontal(id="buttons"):
                yield Button("Done", variant="success", id="done")
                yield Button("Cancel", variant="error", id="cancel")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Tuya Setup"
        self.sub_title = "Device Selection"

        existing = device_config.load_switches(self.path)
        self.existing_ids = {sw.get("id") for sw in existing if sw.get("id")}
        self.existing_ips = {
            sw.get("id"): sw.get("ip", "") for sw in existing if sw.get("id")
        }
        self._selected_ids = set(self.existing_ids)

        try:
            self.cloud_devices = sorted(
                api_client.get_devices(),
                key=lambda d: d.get("name", "").lower(),
            )
        except Exception as exc:
            self.notify(f"Failed to fetch devices: {exc}", severity="error", timeout=10)
            return

        if not self.cloud_devices:
            self.notify(
                "No devices found. Link your Smart Life app in the Tuya Cloud project first.",
                severity="warning",
                timeout=10,
            )
            return

        self._populate_list()
        self._update_status()

    def _populate_list(self, query: str = "") -> None:
        """Rebuild the SelectionList, preserving tracked selections."""
        self._rebuilding = True
        sl = self.query_one("#selections", SelectionList)
        sl.clear_options()

        query_lower = query.lower().strip()
        for dev in self.cloud_devices:
            dev_id = dev.get("id", "")
            name = dev.get("name", "Unnamed")

            if query_lower and query_lower not in name.lower():
                continue

            label = f"{name}  ({dev_id})"
            sl.add_option(
                Selection(label, dev_id, initial_state=dev_id in self._selected_ids)
            )

        self._rebuilding = False

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter the list as user types — save selections first."""
        self._capture_selections()
        self._populate_list(event.value)
        self._update_status()

    def _capture_selections(self) -> None:
        """Merge current SelectionList state into our tracked set."""
        if self._rebuilding:
            return
        sl = self.query_one("#selections", SelectionList)
        self._selected_ids.update(sl.selected)

    def on_selection_list_selected_changed(self) -> None:
        """Ignore selection changes while rebuilding to avoid wiping state."""
        if self._rebuilding:
            return
        sl = self.query_one("#selections", SelectionList)
        self._selected_ids = set(sl.selected)
        self._update_status()

    def _update_status(self) -> None:
        total = len(self.cloud_devices)
        selected = len(self._selected_ids)
        self.query_one("#status", Static).update(f"{selected}/{total} devices selected")

    def action_done(self) -> None:
        self._capture_selections()
        self._write_config()
        self.exit(0)

    def action_cancel(self) -> None:
        self.exit(1)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "done":
            self.action_done()
        elif event.button.id == "cancel":
            self.action_cancel()

    def _write_config(self) -> None:
        if not self._selected_ids:
            self.notify("No devices selected.", severity="warning")
            return

        local = setup_module.scan_local_network() if self.scan else {}

        lines = [
            "# Tuya Smart Switch Configuration",
            "# Auto-generated by 'tuya setup'",
            "# Run 'tuya setup' again to refresh or add new devices.",
            "",
        ]

        for dev in self.cloud_devices:
            dev_id = dev.get("id", "")
            if dev_id not in self._selected_ids:
                continue

            name = dev.get("name", "Unnamed")
            local_key = dev.get("key", "")
            version = dev.get("version", "3.3")
            ip = dev.get("ip", "")

            if not ip and dev_id in local:
                ip = local[dev_id].get("ip", "")
            if not ip and dev_id in self.existing_ips:
                ip = self.existing_ips[dev_id]

            lines.append("[[switch]]")
            lines.append(f'id = "{dev_id}"')
            lines.append(f'name = "{name}"')
            lines.append(f'local_key = "{local_key}"')
            lines.append(f'ip = "{ip or ""}"')
            lines.append(f'version = "{version}"')
            lines.append("")

        content = "\n".join(lines) + "\n"
        with open(self.path, "w") as f:
            f.write(content)

        self.notify(
            f"Wrote {self.path} with {len(self._selected_ids)} device(s).",
            severity="information",
            timeout=5,
        )
        log.info(
            "Textual setup complete",
            path=self.path,
            selected=len(self._selected_ids),
            total=len(self.cloud_devices),
        )


def run_textual_setup(path: str = "switches.toml", scan: bool = True) -> None:
    app = SetupApp(path=path, scan=scan)
    app.run()

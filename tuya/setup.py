import os
import sys

import tinytuya


BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"

ENV_FILE = ".env"
ENV_EXAMPLE_FILE = ".env.example"


def _print_header(text):
    width = 60
    print()
    print(f"{BOLD}{CYAN}{'=' * width}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * width}{RESET}")
    print()


def _print_step(step_num, text):
    print(f"\n{BOLD}{GREEN}[Step {step_num}]{RESET} {text}\n")


def _print_success(text):
    print(f"  {GREEN}✓ {text}{RESET}")


def _print_error(text):
    print(f"  {RED}✗ {text}{RESET}")


def _print_warning(text):
    print(f"  {YELLOW}⚠ {text}{RESET}")


def _print_info(text):
    print(f"  {CYAN}→ {text}{RESET}")


def _prompt(text, default=""):
    suffix = f" [{default}]" if default else ""
    value = input(f"  {text}{suffix}: ").strip()
    return value if value else default


def _prompt_required(text):
    while True:
        value = input(f"  {text}: ").strip()
        if value:
            return value
        _print_error("This field is required.")


def _save_env(data):
    lines = []
    for key, value in data.items():
        lines.append(f'{key}="{value}"')
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _save_env_example():
    content = (
        'CLIENTKEY="<Access ID / Client ID from Tuya IoT Platform>"\n'
        'CLIENTSECRET="<Access Secret / Client Secret from Tuya IoT Platform>"\n'
        'APIREGION="<Data center region: in, eu, us, cn, etc.>"\n'
    )
    with open(ENV_EXAMPLE_FILE, "w", encoding="utf-8") as f:
        f.write(content)


def _test_cloud_connection(api_key, api_secret, api_region):
    try:
        client = tinytuya.Cloud(
            apiRegion=api_region,
            apiKey=api_key,
            apiSecret=api_secret,
        )
        devices = client.getdevices()
        if devices is None:
            return False, "API returned None — check your credentials", None
        if isinstance(devices, list):
            return True, f"Connected! Found {len(devices)} device(s)", client
        return False, f"Unexpected response: {devices}", None
    except Exception as exc:
        error_msg = str(exc)
        if "28841002" in error_msg or "expired" in error_msg.lower():
            return (
                False,
                "Cloud development plan has EXPIRED. Create a new Tuya developer account at https://iot.tuya.com",
                None,
            )
        if "1106" in error_msg or "permission" in error_msg.lower():
            return (
                False,
                "Permission denied — devices not linked to this project. Link your app account first.",
                None,
            )
        return False, f"Connection failed: {error_msg}", None


def _test_local_poll(dev_id, ip, local_key, version):
    try:
        device = tinytuya.Device(dev_id, ip, local_key)
        device.set_version(float(version))
        device.set_socketTimeout(5)
        status = device.status()
        if status and status.get("dps"):
            return True, status.get("dps", {})
        if status and status.get("Error"):
            return False, status.get("Error")
        return False, "No DPS data returned"
    except Exception as exc:
        return False, str(exc)


def run_setup():
    _print_header("Tuya Local Poll Setup Wizard")

    print("  This wizard will guide you through a one-time setup to connect")
    print("  to your Tuya devices. After setup, all data collection happens")
    print("  locally — no internet or cloud API needed.")
    print()
    print("  ┌─────────────────────────────────────────────┐")
    print("  │  Cloud API (internet)  ──one-time──▶  .env   │")
    print("  │       + Local network scan           devices  │")
    print("  │                                     .json     │")
    print("  │                                              │")
    print("  │  After setup:  poll ──local only──▶ data/     │")
    print("  └─────────────────────────────────────────────┘")

    # ── Step 1: Tuya Platform Account ──────────────────────────────
    _print_step(1, "Create a Tuya Developer Account (if you don't have one)")
    print("  1. Go to: https://iot.tuya.com")
    print("  2. Sign up / Log in")
    print("  3. Create a new Cloud Development project")
    print("     - Choose your region (in, eu, us, etc.)")
    print("     - Make sure the free trial plan is ACTIVE")
    print()
    _print_warning("If you get 'plan expired' errors later, create a fresh account.")

    # ── Step 2: Get Credentials ────────────────────────────────────
    _print_step(2, "Enter your Tuya Cloud API credentials")
    print("  Find these on your project dashboard at iot.tuya.com")
    print()

    api_key = _prompt_required("Access ID  (Client ID)")
    api_secret = _prompt_required("Access Secret (Client Secret)")

    print()
    print("  Common regions:")
    print("    in  = India    eu  = Europe    us  = America")
    print("    cn  = China    aw  = West America")
    api_region = _prompt("Region", "in")

    # ── Step 3: Test Connection ────────────────────────────────────
    _print_step(3, "Testing cloud connection...")
    ok, msg, client = _test_cloud_connection(api_key, api_secret, api_region)
    if ok:
        _print_success(msg)
    else:
        _print_error(msg)
        if "expired" in msg.lower():
            _print_warning(
                "Create a new account at https://iot.tuya.com and try again."
            )
        print()
        retry = input("  Fix credentials and retry? (Y/n): ").strip().lower()
        if retry != "n":
            return run_setup()
        _print_error("Setup cancelled.")
        sys.exit(1)

    # ── Step 4: Link App Account ───────────────────────────────────
    _print_step(4, "Link your Smart Life / Tuya app to this project")
    print("  On the Tuya IoT Platform website:")
    print()
    print("  1. Go to your project → Devices → Link App Account")
    print("  2. Click 'Add App Account'")
    print("  3. A QR code will appear")
    print()
    print("  On your phone:")
    print()
    print("  4. Open the 'Tuya Smart' or 'Smart Life' app")
    print("  5. Go to Profile / Me → scan the QR code")
    print("  6. Confirm to link your devices")
    print()
    input("  Press Enter once you've linked your app account...")

    # ── Step 5: Fetch Devices ──────────────────────────────────────
    _print_step(5, "Fetching device details from cloud...")

    from dotenv import load_dotenv
    import os
    os.environ["CLIENTKEY"] = api_key
    os.environ["CLIENTSECRET"] = api_secret
    os.environ["APIREGION"] = api_region

    from . import api_client

    devices = api_client.get_device_details()
    if not devices:
        _print_error("No devices found!")
        print()
        _print_info("Possible reasons:")
        print("    - App account not linked yet (go back to Step 4)")
        print("    - Wrong data center region selected")
        print("    - Devices not added in the Smart Life app")
        print()
        retry = input("  Retry? (Y/n): ").strip().lower()
        if retry != "n":
            return run_setup()
        _print_error("Setup cancelled.")
        sys.exit(1)

    _print_success(f"Found {len(devices)} device(s):")
    for dev in devices:
        name = dev.get("name", dev.get("id"))
        model = dev.get("model", "?")
        dev_id = dev.get("id", "?")
        print(f"    • {name} ({model}) — {dev_id}")

    # ── Step 6: Scan Local Network ─────────────────────────────────
    _print_step(6, "Scanning local network for device IPs...")
    print("  This takes ~18 seconds. Make sure devices are powered on")
    print("  and connected to the same WiFi network.")
    print()

    scan_results = tinytuya.deviceScan(verbose=False, poll=False)

    ip_map = {}
    if scan_results:
        for ip, info in scan_results.items():
            gw_id = info.get("gwId", "")
            if gw_id:
                ip_map[gw_id] = {
                    "ip": ip,
                    "version": str(info.get("version", "3.3")),
                }

    # ── Step 7: Save Everything ────────────────────────────────────
    _print_step(7, "Saving device data...")

    _save_env({
        "CLIENTKEY": api_key,
        "CLIENTSECRET": api_secret,
        "APIREGION": api_region,
    })
    _save_env_example()
    _print_success(f"Credentials saved to {ENV_FILE}")

    import json
    os.makedirs("data", exist_ok=True)

    enriched = []
    cloud = api_client.create_tuya_client()

    for dev in devices:
        dev_id = dev.get("id", "")
        scan_info = ip_map.get(dev_id, {})

        dps_mapping = {}
        try:
            dps_result = cloud.getdps(dev_id)
            if dps_result and dps_result.get("result"):
                for item in dps_result["result"].get("status", []):
                    dp_id = str(item.get("dp_id", ""))
                    dps_mapping[dp_id] = {
                        "code": item.get("code", ""),
                        "type": item.get("type", ""),
                        "values": item.get("values", ""),
                    }
        except Exception:
            pass

        ip_addr = scan_info.get("ip", "")
        version = scan_info.get("version", str(dev.get("version", "3.3")))
        name = dev.get("name", dev_id)
        local_key = dev.get("local_key", dev.get("key", ""))

        entry = {
            "id": dev_id,
            "name": name,
            "local_key": local_key,
            "ip_address": ip_addr,
            "version": version,
            "model": dev.get("model", ""),
            "product_name": dev.get("product_name", ""),
            "category": dev.get("category", ""),
            "mac": dev.get("mac", ""),
            "dps_mapping": dps_mapping,
        }
        enriched.append(entry)

        if ip_addr:
            _print_success(f"{name} → {ip_addr}")
        else:
            _print_warning(f"{name} → no IP found (offline?)")

    devices_file = os.path.join("data", "devices.json")
    with open(devices_file, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2)
        f.write("\n")
    _print_success(f"Device data saved to {devices_file}")

    # ── Step 8: Test Local Poll ────────────────────────────────────
    _print_step(8, "Testing local device polling...")
    for entry in enriched:
        if not all([entry["id"], entry["ip_address"], entry["local_key"]]):
            _print_warning(f"{entry['name']} — skipping (missing IP/key)")
            continue

        ok, result = _test_local_poll(
            entry["id"], entry["ip_address"], entry["local_key"], entry["version"]
        )
        if ok:
            _print_success(f"{entry['name']} — responding with {len(result)} data point(s)")
        else:
            _print_warning(f"{entry['name']} — {result}")

    # ── Done ───────────────────────────────────────────────────────
    _print_header("Setup Complete!")

    print("  You can now DISCONNECT from the internet.")
    print()
    print("  Commands:")
    print(f"    {BOLD}uv run python run.py poll{RESET}         Poll all devices once (local)")
    print(f"    {BOLD}uv run python run.py poll 60{RESET}      Poll every 60 seconds (local)")
    print(f"    {BOLD}uv run python run.py list{RESET}         Show saved devices")
    print()
    print("  Data is saved to: data/readings/<device_name>.jsonl")
    print()

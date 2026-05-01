#!/usr/bin/env python3
"""
Ping / discover local Tuya devices without credentials.

Uses UDP broadcast discovery (tinytuya.deviceScan) and an optional TCP port
sweep on 6668 as a fallback. No device IDs, local keys, or cloud credentials
are required.

Usage:
    uv run python scripts/ping_tuya.py
    # or, if tinytuya is installed globally:
    python3 scripts/ping_tuya.py
"""
from __future__ import annotations

import argparse
import ipaddress
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional


def _discover_tinytuya(timeout: int = 5) -> Dict[str, dict]:
    """UDP broadcast discovery via tinytuya."""
    try:
        import tinytuya
    except ImportError as exc:
        raise SystemExit(
            "tinytuya is not installed. Run: uv sync   (or: pip install tinytuya)"
        ) from exc

    print(f"[*] Sending UDP broadcast discovery (timeout={timeout}s)...")
    try:
        results: Optional[dict] = tinytuya.deviceScan(
            verbose=False, scantime=timeout, poll=False
        )
    except Exception as exc:
        print(f"[!] deviceScan failed: {exc}")
        return {}

    if not results:
        return {}

    cleaned: Dict[str, dict] = {}
    for ip, info in results.items():
        cleaned[ip] = {
            "ip": ip,
            "device_id": info.get("gwId") or info.get("id", ""),
            "version": info.get("version", ""),
            "product_id": info.get("productId", ""),
            "name": info.get("name", ""),
            "source": "udp_broadcast",
        }
    return cleaned


def _check_port(host: str, port: int, timeout: float = 1.5) -> Optional[str]:
    """Try to open a TCP connection; return host if open."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return host
    except (OSError, socket.timeout):
        return None


def _local_subnet() -> str:
    """Best-effort guess of the local /24 subnet."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(("10.254.254.254", 1))
            ip = s.getsockname()[0]
        finally:
            s.close()
        network = ipaddress.IPv4Network(ip + "/24", strict=False)
        return str(network)
    except Exception:
        return "192.168.1.0/24"


def _scan_tcp_port(
    network_cidr: str,
    port: int = 6668,
    max_workers: int = 100,
    timeout: float = 1.0,
) -> List[str]:
    """TCP sweep of a subnet for open Tuya ports."""
    try:
        net = ipaddress.IPv4Network(network_cidr, strict=False)
    except ValueError as exc:
        print(f"[!] Bad network: {exc}")
        return []

    hosts = [str(h) for h in net.hosts()]
    print(f"[*] Scanning {len(hosts)} hosts on {network_cidr}:{port} (TCP)...")

    found: List[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_check_port, h, port, timeout): h for h in hosts}
        for future in as_completed(futures):
            result = future.result()
            if result:
                found.append(result)
                print(f"  [+] {result}:{port} open")
    return found


def _probe_banner(host: str, port: int = 6668, timeout: float = 2.0) -> dict:
    """Connect and try to read the initial device banner (often starts with 0x00...)."""
    info: dict = {"ip": host, "source": "tcp_scan", "banner_hex": "", "banner_readable": ""}
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            data = sock.recv(1024)
            if data:
                info["banner_hex"] = data[:64].hex()
                # Tuya banners often start with nulls; show trimmed preview
                preview = data[:64].replace(b"\x00", b" ").decode("utf-8", "replace").strip()
                info["banner_readable"] = preview
    except Exception as exc:
        info["error"] = str(exc)
    return info


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover local Tuya devices without credentials."
    )
    parser.add_argument(
        "--tcp",
        action="store_true",
        help="Also run a TCP port scan on 6668 (slower but catches silent devices).",
    )
    parser.add_argument(
        "--network",
        default="",
        help="Subnet to scan, e.g. 192.168.1.0/24 (default: auto-detect).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=6668,
        help="TCP port to scan (default: 6668).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="UDP discovery timeout in seconds (default: 5).",
    )
    args = parser.parse_args()

    all_devices: Dict[str, dict] = {}

    # 1) UDP broadcast discovery (fast, credential-free)
    discovered = _discover_tinytuya(timeout=args.timeout)
    for ip, info in discovered.items():
        all_devices[ip] = info

    # 2) Optional TCP sweep
    if args.tcp:
        network = args.network or _local_subnet()
        open_hosts = _scan_tcp_port(network, port=args.port)
        for ip in open_hosts:
            if ip not in all_devices:
                # Try to grab a banner
                extra = _probe_banner(ip, port=args.port)
                all_devices[ip] = {
                    "ip": ip,
                    "device_id": "unknown",
                    "version": "unknown",
                    "product_id": "",
                    "name": "",
                    "source": "tcp_scan",
                    "banner_hex": extra.get("banner_hex", ""),
                    "banner_readable": extra.get("banner_readable", ""),
                }

    # Summary
    print()
    if not all_devices:
        print("[-] No devices found.")
        print("    Tips:")
        print("      • Make sure you're on the same network as the devices.")
        print("      • Some devices only respond when powered / online.")
        print("      • Try again with --tcp for a deeper scan.")
        sys.exit(1)

    print(f"[+] Found {len(all_devices)} device(s):\n")
    print(f"{'IP':<16} {'Device ID':<24} {'Version':<8} {'Source':<14} {'Name / Note'}")
    print("-" * 90)
    for ip, info in sorted(all_devices.items(), key=lambda x: ipaddress.IPv4Address(x[0])):
        dev_id = info.get("device_id") or "unknown"
        version = info.get("version") or "?"
        source = info.get("source", "")
        name = info.get("name") or info.get("banner_readable") or ""
        print(f"{ip:<16} {dev_id:<24} {version:<8} {source:<14} {name}")

    print()
    print("[!] To actually control or poll these devices you still need:")
    print("      • device_id  (shown above as 'Device ID')")
    print("      • local_key  (get it from the Tuya IoT cloud or with tinytuya wizard)")
    print("      • ip_address (shown above)")
    print("      • version    (shown above)")


if __name__ == "__main__":
    main()

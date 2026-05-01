#!/usr/bin/env python3
import socket, ipaddress, concurrent.futures

def scan_tuya():
    # 1. Try tinytuya UDP broadcast
    try:
        import tinytuya
        print("[UDP Broadcast]")
        r = tinytuya.deviceScan(verbose=False, poll=False) or {}
        for ip, info in r.items():
            print(f"  {ip}  id={info.get('gwId','?')}  ver={info.get('version','?')}")
        if r:
            return
        print("  No devices found via broadcast.")
    except ImportError:
        print("tinytuya not installed, trying TCP scan...")

    # 2. Fallback: TCP scan port 6668
    print("[TCP Scan on port 6668]")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    myip = s.getsockname()[0]
    s.close()
    net = str(ipaddress.IPv4Network(myip + "/24", strict=False))
    print(f"  Scanning {net} ...")

    hosts = [str(h) for h in ipaddress.IPv4Network(net).hosts()]
    found = []
    def check(h):
        try:
            with socket.create_connection((h, 6668), timeout=0.8):
                return h
        except:
            return None

    with concurrent.futures.ThreadPoolExecutor(100) as ex:
        for res in concurrent.futures.as_completed({ex.submit(check, h): h for h in hosts}):
            if res.result():
                found.append(res.result())
                print(f"  OPEN: {res.result()}:6668")

    if not found:
        print("  No open ports found.")

if __name__ == "__main__":
    scan_tuya()

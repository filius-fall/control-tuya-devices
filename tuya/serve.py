from __future__ import annotations

import os
import signal
import sys
import time
from typing import List, Optional

from . import logger
from .local import load_devices, poll_devices
from .models import DeviceConfig, PollResult, WebhookConfig
from .webhook import push_webhooks

_running: bool = True


def _signal_handler(signum: int, frame: object) -> None:
    global _running
    _running = False
    print("\nShutting down gracefully...")
    sys.exit(0)


def serve(
    interval_seconds: Optional[int] = None,
    devices: Optional[List[DeviceConfig]] = None,
    webhook_config: Optional[WebhookConfig] = None,
    save: bool = True,
) -> None:
    global _running

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    if interval_seconds is None:
        interval_seconds = int(os.getenv("POLL_INTERVAL", "60"))

    if devices is None:
        devices = load_devices()

    if webhook_config is None:
        webhook_config = WebhookConfig.from_env()

    logger.logs.info(
        "Starting serve mode",
        devices=len(devices),
        interval=interval_seconds,
        webhooks=len(webhook_config.urls),
        batch=webhook_config.batch,
    )

    print(f"  Tuya Polling Service")
    print(f"  Devices:    {len(devices)}")
    print(f"  Interval:   {interval_seconds}s")
    print(f"  Webhooks:   {len(webhook_config.urls)}")
    for url in webhook_config.urls:
        print(f"    → {url}")
    print(f"  Batch mode: {webhook_config.batch}")
    print(f"\n  Press Ctrl+C to stop.\n")

    cycle = 0
    _running = True

    while _running:
        cycle += 1
        try:
            results = poll_devices(devices, save=save)

            online_count = sum(1 for r in results if r.reading.online)
            logger.logs.info(
                "Poll cycle complete",
                cycle=cycle,
                total=len(results),
                online=online_count,
            )

            if webhook_config.enabled and results:
                stats = push_webhooks(results, webhook_config)
                logger.logs.info(
                    "Webhook delivery",
                    sent=stats["sent"],
                    failed=stats["failed"],
                )

            for r in results:
                status = "online" if r.reading.online else "OFFLINE"
                power = f"{r.reading.power_w}W" if r.reading.power_w else ""
                voltage = f"{r.reading.voltage_v}V" if r.reading.voltage_v else ""
                parts = [f"[#{cycle}]", r.reading.device_name, status]
                if voltage:
                    parts.append(voltage)
                if power:
                    parts.append(power)
                print("  " + " | ".join(parts))

        except KeyboardInterrupt:
            break
        except Exception as exc:
            logger.logs.error("Serve cycle failed", error=str(exc), cycle=cycle)

        if _running:
            time.sleep(interval_seconds)

    print("\n  Service stopped.")

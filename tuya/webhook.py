from __future__ import annotations

import os
import time

import requests

from . import logger

log = logger.logs


def _load_config() -> dict:
    return {
        "urls": [
            u.strip()
            for u in os.getenv("WEBHOOK_URLS", "").split(",")
            if u.strip()
        ],
        "timeout": int(os.getenv("WEBHOOK_TIMEOUT", "10")),
        "retries": int(os.getenv("WEBHOOK_RETRIES", "3")),
        "retry_delay": float(os.getenv("WEBHOOK_RETRY_DELAY", "1.0")),
        "batch": os.getenv("WEBHOOK_BATCH", "true").lower() in ("true", "1", "yes"),
    }


def _post_with_retry(
    url: str,
    payload: dict,
    timeout: int,
    retries: int,
    retry_delay: float,
) -> bool:
    for attempt in range(retries):
        try:
            resp = requests.post(
                url,
                json=payload,
                timeout=timeout,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "tuya-exporter/0.2",
                },
            )
            if resp.status_code < 400:
                return True
            log.warning(
                "Webhook returned error",
                url=url,
                status=resp.status_code,
                attempt=attempt + 1,
            )
        except requests.RequestException as exc:
            log.warning(
                "Webhook request failed",
                url=url,
                error=str(exc),
                attempt=attempt + 1,
            )

        if attempt < retries - 1:
            time.sleep(retry_delay)

    return False


def push_webhooks(statuses: list[dict]) -> dict[str, int]:
    config = _load_config()
    if not config["urls"] or not statuses:
        return {"sent": 0, "failed": 0}

    if config["batch"]:
        payloads = [{"readings": statuses}]
    else:
        payloads = [{"reading": s} for s in statuses]

    sent = 0
    failed = 0

    for payload in payloads:
        for url in config["urls"]:
            ok = _post_with_retry(
                url, payload, config["timeout"], config["retries"], config["retry_delay"]
            )
            if ok:
                sent += 1
            else:
                failed += 1
                log.error("Webhook delivery failed after retries", url=url)

    return {"sent": sent, "failed": failed}

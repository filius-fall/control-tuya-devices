from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import requests

from . import logger
from .models import PollResult, WebhookConfig


def _payload_batch(results: List[PollResult]) -> Dict[str, Any]:
    readings = []
    events = []
    for r in results:
        readings.append(r.reading.to_dict())
        if r.event:
            events.append(r.event)
    payload: Dict[str, Any] = {"readings": readings}
    if events:
        payload["events"] = events
    return payload


def _payloads_individual(results: List[PollResult]) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    for r in results:
        entry: Dict[str, Any] = {"reading": r.reading.to_dict()}
        if r.event:
            entry["event"] = r.event
        payloads.append(entry)
    return payloads


def _post_with_retry(
    url: str,
    payload: Dict[str, Any],
    timeout: int,
    retries: int,
    retry_delay: float,
) -> bool:
    for attempt in range(retries):
        try:
            resp: requests.Response = requests.post(
                url,
                json=payload,
                timeout=timeout,
                headers={"Content-Type": "application/json", "User-Agent": "tuya-poll/0.1"},
            )
            if resp.status_code < 400:
                return True
            logger.logs.warning(
                "Webhook returned error",
                url=url,
                status=resp.status_code,
                attempt=attempt + 1,
            )
        except requests.RequestException as exc:
            logger.logs.warning(
                "Webhook request failed",
                url=url,
                error=str(exc),
                attempt=attempt + 1,
            )

        if attempt < retries - 1:
            time.sleep(retry_delay)

    return False


def push_webhooks(
    results: List[PollResult],
    config: WebhookConfig,
) -> Dict[str, int]:
    if not config.enabled or not results:
        return {"sent": 0, "failed": 0}

    if config.batch:
        payloads = [_payload_batch(results)]
    else:
        payloads = _payloads_individual(results)

    sent = 0
    failed = 0

    for payload in payloads:
        for url in config.urls:
            ok: bool = _post_with_retry(
                url, payload, config.timeout, config.retries, config.retry_delay
            )
            if ok:
                sent += 1
            else:
                failed += 1
                logger.logs.error("Webhook delivery failed after retries", url=url)

    return {"sent": sent, "failed": failed}

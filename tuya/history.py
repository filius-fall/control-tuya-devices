"""Fetch historic device logs from the Tuya Cloud.

Tuya Cloud keeps device logs for a limited window (typically 7–30 days).
This module queries DP-report events (evtype=7) to build a recent history.
"""

from datetime import datetime, timezone, timedelta

from . import api_client
from . import logger

log = logger.logs

# Tuya event types: 7 = DP report (data point change)
EVTYPE_DP_REPORT = "7"


def fetch_logs(
    device_id: str,
    hours: int = 24,
    event_types: str = EVTYPE_DP_REPORT,
    max_fetches: int = 10,
) -> list[dict]:
    """Fetch device logs for the past *hours* hours.

    Returns a list of log entry dicts with keys like:
        event_time, event_id, event_type, source, code, value
    """
    client = api_client.get_cloud_client()
    end = 0  # now
    start = -hours / 24  # negative days

    log.info(
        "Fetching device logs",
        device_id=device_id,
        hours=hours,
        max_fetches=max_fetches,
    )

    response = client.getdevicelog(
        deviceid=device_id,
        start=start,
        end=end,
        evtype=event_types,
        max_fetches=max_fetches,
    )

    if not response or not isinstance(response, dict):
        log.warning("Empty or invalid log response", device_id=device_id)
        return []

    if "Error" in response or response.get("success") is False:
        log.warning("Log fetch error", device_id=device_id, error=response)
        return []

    result = response.get("result", {})
    logs = result.get("logs", [])
    log.info(
        "Fetched logs",
        device_id=device_id,
        count=len(logs),
        fetches=response.get("fetches", 1),
    )
    return logs


def summarize_power_logs(device_id: str, hours: int = 24) -> dict:
    """Summarize power-related DP changes from logs.

    Returns a dict with:
        - readings: list of (timestamp, power_value)
        - avg_power: average power in watts (best-effort)
        - max_power: max power observed
        - min_power: min power observed
        - count: number of power readings
    """
    logs = fetch_logs(device_id, hours=hours)
    readings = []

    for entry in logs:
        code = entry.get("code", "")
        if code not in ("cur_power", "add_ele", "total_power", "Power"):
            continue

        value = entry.get("value")
        ts = entry.get("event_time", "")
        try:
            v = float(value)
            # Same heuristics as rich_output
            if v > 10000:
                v = v / 1000
            elif v > 1000:
                v = v / 100
            readings.append((ts, v))
        except (ValueError, TypeError):
            continue

    if not readings:
        return {
            "readings": [],
            "avg_power": None,
            "max_power": None,
            "min_power": None,
            "count": 0,
        }

    values = [v for _, v in readings]
    return {
        "readings": readings,
        "avg_power": sum(values) / len(values),
        "max_power": max(values),
        "min_power": min(values),
        "count": len(values),
    }

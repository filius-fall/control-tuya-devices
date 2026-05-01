from __future__ import annotations

import json
from datetime import datetime, timezone

from . import logger
from . import state_db

log = logger.logs


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    hours = s // 3600
    mins = (s % 3600) // 60
    return f"{hours}h {mins}m {s % 60}s"


def _get_online_state(device_id: str) -> dict | None:
    conn = state_db.connect()
    try:
        row = conn.execute(
            "SELECT state_json FROM device_online_state WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        if row:
            return json.loads(row[0])
        return None
    except Exception:
        return None
    finally:
        conn.close()


def _set_online_state(device_id: str, state: dict) -> None:
    conn = state_db.connect()
    try:
        conn.execute(
            """
            INSERT INTO device_online_state (device_id, state_json)
            VALUES (?, ?)
            ON CONFLICT(device_id) DO UPDATE SET state_json=excluded.state_json
            """,
            (device_id, json.dumps(state)),
        )
        conn.commit()
    finally:
        conn.close()


def track_outage(device_id: str, device_name: str, is_online: bool) -> dict | None:
    prev = _get_online_state(device_id)
    was_online = prev.get("online") if prev else None
    now = _now_iso()
    event = None

    if is_online and was_online is False:
        outage_secs = None
        if prev and prev.get("offline_since"):
            try:
                dt_prev = datetime.fromisoformat(prev["offline_since"])
                dt_now = datetime.fromisoformat(now)
                outage_secs = (dt_now - dt_prev).total_seconds()
            except (ValueError, TypeError):
                pass

        event = {
            "event": "power_restored",
            "device_id": device_id,
            "device_name": device_name,
            "offline_since": prev.get("offline_since") if prev else None,
            "outage_duration_seconds": outage_secs,
        }
        duration_str = (
            f" (was offline for {_format_duration(outage_secs)})"
            if outage_secs
            else ""
        )
        log.info(
            "Power restored",
            device=device_name,
            duration=duration_str,
        )

    elif not is_online and (was_online is True or was_online is None):
        event = {
            "event": "power_lost",
            "device_id": device_id,
            "device_name": device_name,
            "last_seen_online": prev.get("last_online") if prev else None,
        }
        log.info(
            "Power lost",
            device=device_name,
            last_online=prev.get("last_online") if prev else "never",
        )

    new_state = {
        "online": is_online,
        "last_online": now if is_online else (prev.get("last_online") if prev else None),
        "offline_since": None if is_online else now,
    }
    _set_online_state(device_id, new_state)

    return event

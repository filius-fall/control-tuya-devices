"""SQLite-backed storage for discovered devices and cached statuses."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import state_db


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_devices(devices: list[dict], room_map: dict[str, str] | None = None) -> None:
    room_map = room_map or {}
    now = _timestamp()
    conn = state_db.connect()
    try:
        for dev in devices:
            device_id = str(dev.get("id") or "").strip()
            if not device_id:
                continue
            room_name = room_map.get(device_id)
            conn.execute(
                """
                INSERT INTO devices (
                    device_id, name, room_name, version, online, metadata_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    name=excluded.name,
                    room_name=excluded.room_name,
                    version=excluded.version,
                    online=excluded.online,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    device_id,
                    dev.get("name", "unknown"),
                    room_name,
                    dev.get("version"),
                    None if dev.get("online") is None else int(bool(dev.get("online"))),
                    json.dumps(dev, sort_keys=True),
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_devices() -> list[dict]:
    conn = state_db.connect()
    try:
        rows = conn.execute(
            """
            SELECT device_id, name, room_name, version, online, metadata_json
            FROM devices
            ORDER BY lower(name), device_id
            """
        ).fetchall()
    finally:
        conn.close()

    result = []
    for device_id, name, room_name, version, online, metadata_json in rows:
        data = {}
        if metadata_json:
            try:
                data = json.loads(metadata_json)
            except json.JSONDecodeError:
                data = {}
        if not isinstance(data, dict):
            data = {}
        data.update(
            {
                "id": device_id,
                "name": name,
                "room": room_name,
                "version": version or data.get("version", "3.3"),
                "online": None if online is None else bool(online),
            }
        )
        result.append(data)
    return result


def get_device(device_id: str) -> dict | None:
    conn = state_db.connect()
    try:
        row = conn.execute(
            """
            SELECT device_id, name, room_name, version, online, metadata_json
            FROM devices WHERE device_id = ?
            """,
            (device_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None
    data = get_devices()
    for dev in data:
        if dev.get("id") == device_id:
            return dev
    return None


def get_cached_room(device_id: str) -> str | None:
    conn = state_db.connect()
    try:
        row = conn.execute(
            "SELECT room_name FROM devices WHERE device_id = ?", (device_id,)
        ).fetchone()
        return row[0] if row and row[0] else None
    finally:
        conn.close()


def set_status(status: dict) -> None:
    device_id = str(status.get("id") or "").strip()
    if not device_id:
        return
    now = _timestamp()
    conn = state_db.connect()
    try:
        conn.execute(
            """
            INSERT INTO device_status_cache (device_id, status_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                status_json=excluded.status_json,
                updated_at=excluded.updated_at
            """,
            (device_id, json.dumps(status, sort_keys=True), now),
        )
        conn.commit()
    finally:
        conn.close()


def get_statuses() -> list[dict]:
    conn = state_db.connect()
    try:
        rows = conn.execute(
            "SELECT status_json FROM device_status_cache ORDER BY device_id"
        ).fetchall()
    finally:
        conn.close()

    result = []
    for (status_json,) in rows:
        try:
            data = json.loads(status_json)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            result.append(data)
    return result


def get_status(device_id: str) -> dict | None:
    conn = state_db.connect()
    try:
        row = conn.execute(
            "SELECT status_json FROM device_status_cache WHERE device_id = ?",
            (device_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None
    try:
        data = json.loads(row[0])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None

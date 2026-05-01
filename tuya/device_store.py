"""SQLite-backed storage for discovered devices and cached statuses."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import state_db


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_device_row(row) -> dict:
    (
        device_id,
        name,
        room_name,
        version,
        online,
        enabled,
        metadata_json,
        created_at,
        updated_at,
    ) = row
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
            "enabled": bool(enabled),
            "created_at": created_at,
            "updated_at": updated_at,
        }
    )
    return data


def upsert_devices(
    devices: list[dict], room_map: dict[str, str] | None = None
) -> list[dict[str, str]]:
    room_map = room_map or {}
    now = _timestamp()
    conn = state_db.connect()
    changes: list[dict[str, str]] = []
    try:
        for dev in devices:
            device_id = str(dev.get("id") or "").strip()
            if not device_id:
                continue
            room_name = room_map.get(device_id)
            metadata_json = json.dumps(dev, sort_keys=True)
            online = None if dev.get("online") is None else int(bool(dev.get("online")))
            existing = conn.execute(
                """
                SELECT name, room_name, version, online, enabled, metadata_json, created_at, updated_at
                FROM devices WHERE device_id = ?
                """,
                (device_id,),
            ).fetchone()

            if existing is None:
                change_type = "inserted"
                enabled = int(bool(dev.get("enabled", False)))
                conn.execute(
                    """
                    INSERT INTO devices (
                        device_id,
                        name,
                        room_name,
                        version,
                        online,
                        enabled,
                        metadata_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        device_id,
                        dev.get("name", "unknown"),
                        room_name,
                        dev.get("version"),
                        online,
                        enabled,
                        metadata_json,
                        now,
                        now,
                    ),
                )
            else:
                enabled = int(bool(dev.get("enabled", existing[4])))
                previous = {
                    "name": existing[0],
                    "room_name": existing[1],
                    "version": existing[2],
                    "online": existing[3],
                    "enabled": existing[4],
                    "metadata_json": existing[5],
                }
                current = {
                    "name": dev.get("name", "unknown"),
                    "room_name": room_name,
                    "version": dev.get("version"),
                    "online": online,
                    "enabled": enabled,
                    "metadata_json": metadata_json,
                }
                change_type = "updated" if previous != current else "unchanged"
                conn.execute(
                    """
                    UPDATE devices
                    SET name = ?,
                        room_name = ?,
                        version = ?,
                        online = ?,
                        enabled = ?,
                        metadata_json = ?,
                        updated_at = ?
                    WHERE device_id = ?
                    """,
                    (
                        current["name"],
                        current["room_name"],
                        current["version"],
                        current["online"],
                        current["enabled"],
                        current["metadata_json"],
                        now,
                        device_id,
                    ),
                )

            changes.append(
                {
                    "device_id": device_id,
                    "name": dev.get("name", "unknown"),
                    "change": change_type,
                }
            )
        conn.commit()
    finally:
        conn.close()
    return changes


def get_devices() -> list[dict]:
    conn = state_db.connect()
    try:
        rows = conn.execute(
            """
            SELECT device_id, name, room_name, version, online, enabled, metadata_json, created_at, updated_at
            FROM devices
            ORDER BY lower(name), device_id
            """
        ).fetchall()
    finally:
        conn.close()

    return [_normalize_device_row(row) for row in rows]


def get_device(device_id: str) -> dict | None:
    conn = state_db.connect()
    try:
        row = conn.execute(
            """
            SELECT device_id, name, room_name, version, online, enabled, metadata_json, created_at, updated_at
            FROM devices WHERE device_id = ?
            """,
            (device_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None
    return _normalize_device_row(row)


def set_device_enabled(device_id: str, enabled: bool) -> bool:
    conn = state_db.connect()
    try:
        cur = conn.execute(
            "UPDATE devices SET enabled = ?, updated_at = ? WHERE device_id = ?",
            (int(bool(enabled)), _timestamp(), device_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_enabled_devices() -> list[dict]:
    return [dev for dev in get_devices() if dev.get("enabled")]


def get_cached_room(device_id: str) -> str | None:
    conn = state_db.connect()
    try:
        row = conn.execute(
            "SELECT room_name FROM devices WHERE device_id = ?", (device_id,)
        ).fetchone()
        return row[0] if row and row[0] else None
    finally:
        conn.close()


def update_device_network_info(
    device_id: str, ip: str | None = None, version: str | None = None
) -> bool:
    """Update IP and/or version for a cached device and bump updated_at."""
    now = _timestamp()
    conn = state_db.connect()
    try:
        fields = ["updated_at = ?"]
        params: list = [now]
        if ip is not None:
            fields.append("ip = ?")
            params.append(ip)
        if version is not None:
            fields.append("version = ?")
            params.append(version)
        params.append(device_id)
        sql = f"UPDATE devices SET {', '.join(fields)} WHERE device_id = ?"
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount > 0
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

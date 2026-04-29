"""Room override storage backed by SQLite.

Provides persistent, crash-safe storage for manual room assignments.
Overrides take precedence over API-discovered rooms.
"""

import sqlite3
import os

DB_PATH = os.getenv("TUYA_ROOM_DB", "rooms.db")


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS device_rooms (
            device_id TEXT PRIMARY KEY,
            room_name TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def get_overrides() -> dict[str, str]:
    """Return all device_id -> room_name overrides."""
    conn = _connect()
    rows = conn.execute("SELECT device_id, room_name FROM device_rooms").fetchall()
    conn.close()
    return {device_id: room_name for device_id, room_name in rows}


def get_room(device_id: str) -> str | None:
    """Return the override room for a device, or None if not set."""
    conn = _connect()
    row = conn.execute(
        "SELECT room_name FROM device_rooms WHERE device_id = ?", (device_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def set_room(device_id: str, room_name: str) -> None:
    """Assign a single device to a room."""
    conn = _connect()
    conn.execute(
        """
        INSERT INTO device_rooms (device_id, room_name)
        VALUES (?, ?)
        ON CONFLICT(device_id) DO UPDATE SET room_name=excluded.room_name
        """,
        (device_id, room_name),
    )
    conn.commit()
    conn.close()


def set_rooms(mapping: dict[str, str]) -> None:
    """Bulk-assign devices to rooms."""
    conn = _connect()
    for device_id, room_name in mapping.items():
        conn.execute(
            """
            INSERT INTO device_rooms (device_id, room_name)
            VALUES (?, ?)
            ON CONFLICT(device_id) DO UPDATE SET room_name=excluded.room_name
            """,
            (device_id, room_name),
        )
    conn.commit()
    conn.close()


def delete_room(device_id: str) -> None:
    """Remove a room override for a device."""
    conn = _connect()
    conn.execute("DELETE FROM device_rooms WHERE device_id = ?", (device_id,))
    conn.commit()
    conn.close()


def resolve_room(device_id: str, api_room: str | None = None) -> str:
    """Return the effective room for a device.

    Priority: override > API > unknown
    """
    override = get_room(device_id)
    if override:
        return override
    if api_room:
        return api_room
    return "unknown"

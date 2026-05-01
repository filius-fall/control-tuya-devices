"""Room override storage backed by the shared SQLite state DB.

Overrides take precedence over API-discovered rooms.
"""

from . import state_db


def get_overrides() -> dict[str, str]:
    """Return all device_id -> room_name overrides."""
    conn = state_db.connect()
    try:
        rows = conn.execute("SELECT device_id, room_name FROM device_rooms").fetchall()
        return {device_id: room_name for device_id, room_name in rows}
    finally:
        conn.close()


def get_room(device_id: str) -> str | None:
    """Return the override room for a device, or None if not set."""
    conn = state_db.connect()
    try:
        row = conn.execute(
            "SELECT room_name FROM device_rooms WHERE device_id = ?", (device_id,)
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def set_room(device_id: str, room_name: str) -> None:
    """Assign a single device to a room."""
    conn = state_db.connect()
    try:
        conn.execute(
            """
            INSERT INTO device_rooms (device_id, room_name)
            VALUES (?, ?)
            ON CONFLICT(device_id) DO UPDATE SET room_name=excluded.room_name
            """,
            (device_id, room_name),
        )
        conn.commit()
    finally:
        conn.close()


def set_rooms(mapping: dict[str, str]) -> None:
    """Bulk-assign devices to rooms."""
    conn = state_db.connect()
    try:
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
    finally:
        conn.close()


def delete_room(device_id: str) -> None:
    """Remove a room override for a single device."""
    conn = state_db.connect()
    try:
        conn.execute("DELETE FROM device_rooms WHERE device_id = ?", (device_id,))
        conn.commit()
    finally:
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

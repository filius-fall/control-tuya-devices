"""Shared SQLite storage for exporter state."""

import os
import sqlite3
from datetime import datetime, timezone

DEFAULT_DB_PATH = "tuya.db"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def get_db_path() -> str:
    """Return the configured SQLite path for exporter state."""
    return os.getenv("TUYA_DB_PATH", DEFAULT_DB_PATH)


def connect() -> sqlite3.Connection:
    """Open the shared SQLite database and ensure required tables exist."""
    path = get_db_path()
    if path != ":memory:":
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS device_rooms (
            device_id TEXT PRIMARY KEY,
            room_name TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS device_energy (
            device_id TEXT PRIMARY KEY,
            total_joules REAL NOT NULL DEFAULT 0,
            last_raw_kwh REAL,
            reset_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            room_name TEXT,
            version TEXT,
            online INTEGER,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS device_status_cache (
            device_id TEXT PRIMARY KEY,
            status_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS device_online_state (
            device_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL
        )
        """
    )
    _ensure_column(conn, "devices", "created_at", "created_at TEXT")
    _ensure_column(conn, "devices", "updated_at", "updated_at TEXT")
    now = _timestamp()
    conn.execute(
        """
        UPDATE devices
        SET created_at = COALESCE(created_at, ?),
            updated_at = COALESCE(updated_at, ?)
        WHERE created_at IS NULL OR updated_at IS NULL
        """,
        (now, now),
    )
    conn.commit()
    return conn

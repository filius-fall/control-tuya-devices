import os
import sqlite3
import time
import unittest
from tempfile import TemporaryDirectory

from tuya import device_store


class DeviceStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = os.path.join(self.temp_dir.name, "tuya.db")
        self.old_db_path = os.environ.get("TUYA_DB_PATH")
        os.environ["TUYA_DB_PATH"] = self.db_path
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        if self.old_db_path is None:
            os.environ.pop("TUYA_DB_PATH", None)
        else:
            os.environ["TUYA_DB_PATH"] = self.old_db_path

    def test_upsert_sets_created_and_updated_timestamps(self):
        changes = device_store.upsert_devices(
            [{"id": "device-1", "name": "Desk", "version": "3.3", "online": True}]
        )

        device = device_store.get_device("device-1")
        self.assertIsNotNone(device)
        self.assertTrue(device["created_at"])
        self.assertTrue(device["updated_at"])
        self.assertFalse(device["enabled"])
        self.assertEqual(device["created_at"], device["updated_at"])
        self.assertEqual(changes[0]["change"], "inserted")

    def test_upsert_preserves_created_at_and_updates_updated_at(self):
        device_store.upsert_devices(
            [{"id": "device-1", "name": "Desk", "version": "3.3", "online": True}]
        )
        first = device_store.get_device("device-1")

        time.sleep(0.01)
        changes = device_store.upsert_devices(
            [{"id": "device-1", "name": "Desk 2", "version": "3.4", "online": False}]
        )
        second = device_store.get_device("device-1")

        self.assertEqual(first["created_at"], second["created_at"])
        self.assertNotEqual(first["updated_at"], second["updated_at"])
        self.assertEqual(second["name"], "Desk 2")
        self.assertEqual(second["version"], "3.4")
        self.assertFalse(second["online"])
        self.assertEqual(changes[0]["change"], "updated")

    def test_upsert_reports_unchanged_rows(self):
        device_store.upsert_devices(
            [{"id": "device-1", "name": "Desk", "version": "3.3", "online": True}]
        )

        changes = device_store.upsert_devices(
            [{"id": "device-1", "name": "Desk", "version": "3.3", "online": True}]
        )

        self.assertEqual(changes[0]["change"], "unchanged")

    def test_existing_database_gets_missing_timestamp_columns(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE devices (
                    device_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    room_name TEXT,
                    version TEXT,
                    online INTEGER,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO devices (
                    device_id, name, room_name, version, online, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("device-1", "Desk", None, "3.3", 1, "{}", "2026-05-01T00:00:00+00:00"),
            )
            conn.commit()
        finally:
            conn.close()

        devices = device_store.get_devices()

        self.assertEqual(len(devices), 1)
        self.assertTrue(devices[0]["created_at"])
        self.assertTrue(devices[0]["updated_at"])
        self.assertFalse(devices[0]["enabled"])

    def test_can_enable_device(self):
        device_store.upsert_devices(
            [{"id": "device-1", "name": "Desk", "version": "3.3", "online": True}]
        )

        updated = device_store.set_device_enabled("device-1", True)

        self.assertTrue(updated)
        self.assertTrue(device_store.get_device("device-1")["enabled"])


if __name__ == "__main__":
    unittest.main()

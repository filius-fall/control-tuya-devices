import os
import sqlite3
import unittest
from tempfile import TemporaryDirectory

from tuya.energy_tracker import EnergyTracker, KWH_TO_JOULES
from tuya import room_config


class EnergyTrackerTest(unittest.TestCase):
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

    def test_first_sample_sets_baseline_without_incrementing_total(self):
        tracker = EnergyTracker()

        state = tracker.update("device-1", 1.2)

        self.assertEqual(state.device_id, "device-1")
        self.assertAlmostEqual(state.total_joules, 0.0)
        self.assertAlmostEqual(state.last_raw_kwh, 1.2)
        self.assertEqual(state.reset_count, 0)

    def test_monotonic_readings_increment_total_energy(self):
        tracker = EnergyTracker()
        tracker.update("device-1", 1.2)

        state = tracker.update("device-1", 1.7)

        self.assertAlmostEqual(state.total_joules, 0.5 * KWH_TO_JOULES)
        self.assertAlmostEqual(state.last_raw_kwh, 1.7)
        self.assertEqual(state.reset_count, 0)

    def test_reset_is_treated_as_new_day_and_increments_reset_counter(self):
        tracker = EnergyTracker()
        tracker.update("device-1", 0.5)
        tracker.update("device-1", 1.5)

        state = tracker.update("device-1", 0.2)

        expected_joules = (1.0 + 0.2) * KWH_TO_JOULES
        self.assertAlmostEqual(state.total_joules, expected_joules)
        self.assertAlmostEqual(state.last_raw_kwh, 0.2)
        self.assertEqual(state.reset_count, 1)

    def test_state_is_persisted_and_loaded_from_shared_db(self):
        tracker = EnergyTracker()
        tracker.update("device-1", 0.5)
        tracker.update("device-1", 1.0)

        reloaded = EnergyTracker()
        state = reloaded.snapshot()["device-1"]

        self.assertAlmostEqual(state.total_joules, 0.5 * KWH_TO_JOULES)
        self.assertAlmostEqual(state.last_raw_kwh, 1.0)
        self.assertEqual(state.reset_count, 0)

    def test_rooms_and_energy_share_one_sqlite_database(self):
        room_config.set_room("device-1", "office")
        tracker = EnergyTracker()
        tracker.update("device-1", 0.8)

        conn = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        finally:
            conn.close()

        self.assertIn("device_rooms", tables)
        self.assertIn("device_energy", tables)
        self.assertEqual(room_config.get_room("device-1"), "office")


if __name__ == "__main__":
    unittest.main()

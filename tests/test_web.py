import importlib
import math
import os
import unittest
from unittest import mock


os.environ["TUYA_DISABLE_POLL_THREAD"] = "1"

from tuya import device_store, web  # noqa: E402


class WebMetricsTest(unittest.TestCase):
    def setUp(self):
        self.old_db_path = os.environ.get("TUYA_DB_PATH")
        self.temp_db = os.path.join(os.getcwd(), "test-web.db")
        os.environ["TUYA_DB_PATH"] = self.temp_db
        try:
            os.remove(self.temp_db)
        except FileNotFoundError:
            pass
        importlib.reload(device_store)
        importlib.reload(web)
        self.client = web.flask_app.test_client()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        if self.old_db_path is None:
            os.environ.pop("TUYA_DB_PATH", None)
        else:
            os.environ["TUYA_DB_PATH"] = self.old_db_path
        try:
            os.remove(self.temp_db)
        except FileNotFoundError:
            pass

    def _dev(self, **overrides):
        dev = {
            "id": "device-1",
            "name": "AC 1",
            "online": True,
            "version": "3.3",
            "key": "local-key",
            "last_ip": "192.168.1.10",
        }
        dev.update(overrides)
        return dev

    def test_offline_device_reports_zero_usage(self):
        with mock.patch.object(
            web.local_client,
            "get_device_status_local",
            return_value=None,
        ), mock.patch.object(web.api_client, "get_device_status") as cloud_status:
            status = web._poll_device(self._dev())

        self.assertFalse(status["online"])
        self.assertEqual(web.ONLINE.labels(device_id="device-1")._value.get(), 0)
        self.assertEqual(web.POWER.labels(device_id="device-1")._value.get(), 0)
        self.assertEqual(web.CURRENT.labels(device_id="device-1")._value.get(), 0)
        self.assertTrue(
            math.isnan(web.VOLTAGE.labels(device_id="device-1")._value.get())
        )
        cloud_status.assert_not_called()

    def test_off_device_clears_stale_power_and_current_to_zero(self):
        with mock.patch.object(
            web.local_client,
            "get_device_status_local",
            return_value={
                "dps": {
                    "switch_1": True,
                    "cur_power": 2500,
                    "cur_current": 1200,
                    "cur_voltage": 2310,
                }
            },
        ):
            web._poll_device(self._dev())

        with mock.patch.object(
            web.local_client,
            "get_device_status_local",
            return_value={
                "dps": {
                    "switch_1": False,
                    "cur_voltage": 2290,
                }
            },
        ):
            status = web._poll_device(self._dev())

        self.assertTrue(status["online"])
        self.assertFalse(status["on"])
        self.assertEqual(web.POWER.labels(device_id="device-1")._value.get(), 0)
        self.assertEqual(web.CURRENT.labels(device_id="device-1")._value.get(), 0)
        self.assertEqual(web.SWITCH.labels(device_id="device-1")._value.get(), 0)
        self.assertEqual(web.VOLTAGE.labels(device_id="device-1")._value.get(), 229.0)

    def test_poll_all_persists_statuses_in_sqlite_cache(self):
        device_store.upsert_devices([self._dev()])

        with mock.patch.object(
            web.local_client,
            "get_device_status_local",
            return_value={
                "dps": {
                    "switch_1": False,
                    "cur_voltage": 2290,
                }
            },
        ):
            web._poll_all()

        status = device_store.get_status("device-1")
        self.assertIsNotNone(status)
        self.assertEqual(status["id"], "device-1")
        self.assertFalse(status["on"])
        self.assertEqual(status["source"], "local")

    def test_refresh_json_surfaces_error_message(self):
        with mock.patch.object(
            web,
            "_discover_devices",
            side_effect=RuntimeError("quota exhausted"),
        ):
            response = self.client.post(
                "/refresh", headers={"Accept": "application/json"}
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "quota exhausted")

        state = self.client.get("/api/state")
        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.get_json()["last_refresh_error"], "quota exhausted")


if __name__ == "__main__":
    unittest.main()

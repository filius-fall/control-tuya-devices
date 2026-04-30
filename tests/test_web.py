import importlib
import math
import os
import unittest
from unittest import mock


os.environ["TUYA_DISABLE_POLL_THREAD"] = "1"

from tuya import web  # noqa: E402


class WebMetricsTest(unittest.TestCase):
    def setUp(self):
        importlib.reload(web)

    def _dev(self, **overrides):
        dev = {
            "id": "device-1",
            "name": "AC 1",
            "online": True,
            "version": "3.3",
        }
        dev.update(overrides)
        return dev

    def test_offline_device_reports_zero_usage(self):
        status = web._poll_device(self._dev(online=False))

        self.assertFalse(status["online"])
        self.assertEqual(web.ONLINE.labels(device_id="device-1")._value.get(), 0)
        self.assertEqual(web.POWER.labels(device_id="device-1")._value.get(), 0)
        self.assertEqual(web.CURRENT.labels(device_id="device-1")._value.get(), 0)
        self.assertTrue(
            math.isnan(web.VOLTAGE.labels(device_id="device-1")._value.get())
        )

    def test_off_device_clears_stale_power_and_current_to_zero(self):
        with mock.patch.object(
            web.api_client,
            "get_device_status",
            return_value={
                "result": [
                    {"code": "switch_1", "value": True},
                    {"code": "cur_power", "value": 2500},
                    {"code": "cur_current", "value": 1200},
                    {"code": "cur_voltage", "value": 2310},
                ]
            },
        ):
            web._poll_device(self._dev())

        with mock.patch.object(
            web.api_client,
            "get_device_status",
            return_value={
                "result": [
                    {"code": "switch_1", "value": False},
                    {"code": "cur_voltage", "value": 2290},
                ]
            },
        ):
            status = web._poll_device(self._dev())

        self.assertTrue(status["online"])
        self.assertFalse(status["on"])
        self.assertEqual(web.POWER.labels(device_id="device-1")._value.get(), 0)
        self.assertEqual(web.CURRENT.labels(device_id="device-1")._value.get(), 0)
        self.assertEqual(web.SWITCH.labels(device_id="device-1")._value.get(), 0)
        self.assertEqual(web.VOLTAGE.labels(device_id="device-1")._value.get(), 229.0)


if __name__ == "__main__":
    unittest.main()

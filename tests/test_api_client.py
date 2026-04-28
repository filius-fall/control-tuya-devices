import unittest
from unittest import mock

from tuya import api_client, config


class FakeTuyaClient:
    def getdevices(self):
        return [{"id": "device-1"}]


class ApiClientTest(unittest.TestCase):
    def test_get_device_details_accepts_injected_client(self):
        self.assertEqual(
            api_client.get_device_details(FakeTuyaClient()),
            [{"id": "device-1"}],
        )

    def test_require_tuya_settings_reports_missing_values(self):
        with (
            mock.patch.object(config, "CLIENTKEY", None),
            mock.patch.object(config, "CLIENTSECRET", "secret"),
            mock.patch.object(config, "APIREGION", "in"),
        ):
            with self.assertRaisesRegex(RuntimeError, "CLIENTKEY"):
                config.require_tuya_settings()


if __name__ == "__main__":
    unittest.main()

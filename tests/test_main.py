import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tuya.main import append_json_array, read_json_array


class JsonPersistenceTest(unittest.TestCase):
    def test_append_json_array_creates_new_file(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "api_response.json"
            data = append_json_array(file_path, {"id": "device-1"})

            self.assertEqual(data, [{"id": "device-1"}])
            self.assertEqual(json.loads(file_path.read_text(encoding="utf-8")), data)

    def test_append_json_array_preserves_existing_entries(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "api_response.json"
            file_path.write_text('[{"id": "device-1"}]', encoding="utf-8")

            data = append_json_array(file_path, {"id": "device-2"})

            self.assertEqual(data, [{"id": "device-1"}, {"id": "device-2"}])
            self.assertEqual(json.loads(file_path.read_text(encoding="utf-8")), data)

    def test_read_json_array_rejects_invalid_json(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "api_response.json"
            file_path.write_text("{not-json", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Invalid JSON"):
                read_json_array(file_path)

    def test_read_json_array_rejects_non_array_json(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "api_response.json"
            file_path.write_text('{"id": "device-1"}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON array"):
                read_json_array(file_path)


if __name__ == "__main__":
    unittest.main()

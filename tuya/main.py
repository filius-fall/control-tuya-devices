import os
import json

from . import logger
from . import api_client


def read_json_array(file_path):
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return []

    with open(file_path, "r", encoding="utf-8") as file:
        try:
            data = json.load(file)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {file_path}") from exc

    if not isinstance(data, list):
        raise ValueError(f"Expected {file_path} to contain a JSON array")

    return data


def append_json_array(file_path, item):
    data = read_json_array(file_path)
    data.append(item)

    temp_path = f"{file_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
        file.write("\n")

    os.replace(temp_path, file_path)
    return data


def main():
    devices = api_client.get_device_details()

    os.makedirs("data", exist_ok=True)
    file_path = os.path.join("data", "api_response.json")

    data = append_json_array(file_path, devices)
    logger.logs.info("Saved Tuya API response", file_path=file_path, records=len(data))


if __name__ == "__main__":
    main()

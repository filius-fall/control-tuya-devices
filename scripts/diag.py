"""Quick diagnostic: fetch raw device status and print all DPs."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tuya import api_client, logger

logger.logs.bind()

if len(sys.argv) < 2:
    print(f"Usage: python {sys.argv[0]} <device_id>")
    print("Example: python scripts/diag.py bf1234567890abcdef1234")
    sys.exit(1)

dev_id = sys.argv[1]
status = api_client.get_device_status(dev_id)

print("\n=== Raw status ===")
import json
print(json.dumps(status, indent=2))

print("\n=== Extracted DPs ===")
from tuya.rich_output import _extract_power_dps
if status and "result" in status:
    result = status["result"]
    if isinstance(result, list):
        dps = {item["code"]: item.get("value") for item in result if isinstance(item, dict) and "code" in item}
    elif isinstance(result, dict):
        dps = result.get("status") or result
    else:
        dps = {}
    print(json.dumps(dps, indent=2))
    print("\n=== Power DPs ===")
    print(json.dumps(_extract_power_dps(dps), indent=2))
else:
    print("No result in status")

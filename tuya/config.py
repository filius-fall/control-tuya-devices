import os
from typing import Dict, Optional

from dotenv import load_dotenv

load_dotenv()

CLIENTKEY: Optional[str] = os.getenv("CLIENTKEY")
CLIENTSECRET: Optional[str] = os.getenv("CLIENTSECRET")
APIREGION: Optional[str] = os.getenv("APIREGION")


def require_tuya_settings() -> Dict[str, str]:
    missing: list[str] = [
        name
        for name, value in {
            "CLIENTKEY": CLIENTKEY,
            "CLIENTSECRET": CLIENTSECRET,
            "APIREGION": APIREGION,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    return {
        "api_key": CLIENTKEY or "",
        "api_secret": CLIENTSECRET or "",
        "api_region": APIREGION or "",
    }

import os

from dotenv import load_dotenv

load_dotenv()

CLIENT_KEY = os.getenv("CLIENTKEY")
CLIENT_SECRET = os.getenv("CLIENTSECRET")
API_REGION = os.getenv("APIREGION")


def require_tuya_settings():
    """Return Tuya credentials or raise a clear configuration error."""
    missing = [
        name
        for name, value in {
            "CLIENTKEY": CLIENT_KEY,
            "CLIENTSECRET": CLIENT_SECRET,
            "APIREGION": API_REGION,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    return {
        "api_key": CLIENT_KEY,
        "api_secret": CLIENT_SECRET,
        "api_region": API_REGION,
    }

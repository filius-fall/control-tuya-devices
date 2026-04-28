import os

from dotenv import load_dotenv

load_dotenv()

CLIENTKEY = os.getenv("CLIENTKEY")
CLIENTSECRET = os.getenv("CLIENTSECRET")
APIREGION = os.getenv("APIREGION")


def require_tuya_settings():
    """Return Tuya credentials or raise a clear configuration error."""
    missing = [
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
        "api_key": CLIENTKEY,
        "api_secret": CLIENTSECRET,
        "api_region": APIREGION,
    }

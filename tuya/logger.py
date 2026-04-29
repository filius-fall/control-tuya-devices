import structlog
import logging
import sys
import os

logger = logging.getLogger("tuya")
logger.propagate = False

# Allow forcing file logging via env var; default to stdout for systemd.
_LOG_TO_FILE = os.getenv("TUYA_LOG_FILE", "").lower() in ("1", "true", "yes")
_LOG_FORMAT = os.getenv("TUYA_LOG_FORMAT", "json").lower()
_LOG_LEVEL = os.getenv("TUYA_LOG_LEVEL", "INFO").upper()
_log_level = getattr(logging, _LOG_LEVEL, logging.INFO)

logger.setLevel(_log_level)

if not logger.handlers:
    if _LOG_TO_FILE:
        os.makedirs("logs", exist_ok=True)
        handler = logging.FileHandler("logs/app.log")
    else:
        handler = logging.StreamHandler(sys.stdout)

    handler.setLevel(_log_level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

_processors = [
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.TimeStamper(fmt="iso"),
]

if _LOG_FORMAT == "console":
    _processors.append(structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()))
else:
    _processors.append(structlog.processors.JSONRenderer())

structlog.configure(
    processors=_processors,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.make_filtering_bound_logger(_log_level),
)
logs = structlog.get_logger("tuya")

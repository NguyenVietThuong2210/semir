"""
Logging utilities: request ID tracking + JSON formatter.

Usage in views/services:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Importing customers", extra={"step": "import_customers"})
    # request_id is injected automatically by RequestIDMiddleware
"""

import json
import logging
import threading

_local = threading.local()


# ---------------------------------------------------------------------------
# Request ID thread-local helpers
# ---------------------------------------------------------------------------

def set_request_id(request_id: str) -> None:
    _local.request_id = request_id


def get_request_id() -> str | None:
    return getattr(_local, "request_id", None)


def clear_request_id() -> None:
    _local.request_id = None


# ---------------------------------------------------------------------------
# Logging filter — injects request_id + step into every record
# ---------------------------------------------------------------------------

class RequestIDFilter(logging.Filter):
    """Adds ``request_id`` and ``step`` fields to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        if not hasattr(record, "step"):
            record.step = "-"
        return True


# ---------------------------------------------------------------------------
# JSON formatter — Loki-friendly structured output
# ---------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    """
    Emits one JSON object per line. Fields:
        time, level, logger, module, request_id, step, message[, exception]

    Filter in Grafana/Loki with:
        {service="semir_web"} | json | request_id="abc123"
        {service="semir_web"} | json | step="sync_customers"
        {service="semir_web"} | json | level="ERROR"
    """

    def format(self, record: logging.LogRecord) -> str:
        data: dict = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "request_id": getattr(record, "request_id", "-"),
            "step": getattr(record, "step", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)

"""App/views/admin_logs.py — Admin log viewer page.

Reads the last 50 INFO, WARNING, and ERROR log entries from the rotating
JSON log files and renders them in a three-table dashboard.

Access: superuser only (/admin-logs/).
"""
import json
import os
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render

from django.conf import settings


_LOGS_DIR = Path(getattr(settings, "LOGS_DIR", os.path.join(settings.BASE_DIR, "logs")))

# Log files to read (in priority order for each level)
_LOG_FILES = {
    "INFO":    [_LOGS_DIR / "app.log", _LOGS_DIR / "cnv_sync.log"],
    "WARNING": [_LOGS_DIR / "app.log", _LOGS_DIR / "cnv_sync.log", _LOGS_DIR / "errors.log"],
    "ERROR":   [_LOGS_DIR / "errors.log", _LOGS_DIR / "app.log", _LOGS_DIR / "cnv_sync.log"],
}
_LIMIT = 50


def _read_json_log(paths: list, level_filter: str | None = None, limit: int = _LIMIT) -> list:
    """
    Read the last `limit` JSON log lines from the given file paths.

    Each line is a JSON object written by JsonFormatter.
    Files are read tail-first (newest entries first).
    If level_filter is given, only records with that exact level are returned.
    Deduplicates by (time, message) across files.
    """
    seen = set()
    entries = []

    for path in paths:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        lines = [l for l in text.splitlines() if l.strip()]
        # Iterate newest-first
        for line in reversed(lines):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if level_filter and record.get("level") != level_filter:
                continue
            key = (record.get("time"), record.get("message"))
            if key in seen:
                continue
            seen.add(key)
            entries.append(record)
            if len(entries) >= limit:
                break
        if len(entries) >= limit:
            break

    return entries  # already newest-first


@login_required
def admin_logs(request):
    """Admin log viewer: 3 tables showing latest INFO / WARNING / ERROR entries."""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Superuser access required.")

    info_entries    = _read_json_log(_LOG_FILES["INFO"],    level_filter="INFO")
    warning_entries = _read_json_log(_LOG_FILES["WARNING"], level_filter="WARNING")
    error_entries   = _read_json_log(_LOG_FILES["ERROR"],   level_filter="ERROR")

    return render(request, "admin/log_viewer.html", {
        "info_entries":    info_entries,
        "warning_entries": warning_entries,
        "error_entries":   error_entries,
        "limit":           _LIMIT,
        "logs_dir":        str(_LOGS_DIR),
    })

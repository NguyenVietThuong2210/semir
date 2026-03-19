"""
App/upload_jobs.py — Thread-safe in-memory job store for background uploads.
"""
import io
import threading
import uuid
from datetime import datetime, timezone


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 with +00:00 so browsers parse it correctly."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

_jobs: dict = {}
_lock = threading.Lock()
_MAX_JOBS = 100

JOB_TYPE_LABELS = {
    "customers":   "Customer Data",
    "used_points": "Used Points",
    "sales":       "Sales Transactions",
    "coupons":     "Coupon Data",
}


class NamedBytesIO(io.BytesIO):
    """BytesIO with a .name attribute so read_file() can detect csv/xlsx."""
    def __init__(self, data: bytes, name: str):
        super().__init__(data)
        self.name = name


def create_job(job_type: str, filename: str) -> str:
    job_id = str(uuid.uuid4())
    job = {
        "id":          job_id,
        "type":        job_type,
        "type_label":  JOB_TYPE_LABELS.get(job_type, job_type),
        "filename":    filename,
        "status":      "queued",       # queued | running | done | error
        "started_at":  _now_iso(),
        "finished_at": None,
        "processed":   0,
        "total":       0,
        "result":      None,
        "error":       None,
    }
    with _lock:
        _jobs[job_id] = job
        if len(_jobs) > _MAX_JOBS:
            oldest_keys = sorted(_jobs, key=lambda k: _jobs[k]["started_at"])[: len(_jobs) - _MAX_JOBS]
            for k in oldest_keys:
                del _jobs[k]
    return job_id


def update_job(job_id: str, **kwargs) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def get_job(job_id: str) -> dict:
    with _lock:
        return dict(_jobs.get(job_id, {}))


def get_recent_jobs(limit: int = 20) -> list:
    with _lock:
        jobs = sorted(_jobs.values(), key=lambda j: j["started_at"], reverse=True)
        return [dict(j) for j in jobs[:limit]]


def make_progress_fn(job_id: str):
    """Return a callback: progress_fn(processed, total) → updates job progress."""
    def _fn(processed: int, total: int):
        update_job(job_id, processed=processed, total=total)
    return _fn

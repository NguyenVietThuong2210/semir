"""
App/upload_jobs.py — Upload job store backed by Django cache (Redis).
Shared across all gunicorn workers.
"""
import io
import threading
import uuid
from datetime import datetime, timedelta, timezone

_lock = threading.Lock()   # guards index read-modify-write within a single worker
_MAX_JOBS = 100
_JOB_TTL  = 86400          # 24 h

JOB_TYPE_LABELS = {
    "customers":   "Customer Data",
    "used_points": "Used Points",
    "sales":       "Sales Transactions",
    "coupons":     "Coupon Data",
}

_INDEX_KEY    = "upload_jobs_index"     # list of {"id": ..., "started_at": ...}
_JOB_KEY_PFX  = "upload_job:"          # + job_id


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 with +00:00 so browsers parse it correctly."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _jkey(job_id: str) -> str:
    return f"{_JOB_KEY_PFX}{job_id}"


class NamedBytesIO(io.BytesIO):
    """BytesIO with a .name attribute so read_file() can detect csv/xlsx."""
    def __init__(self, data: bytes, name: str):
        super().__init__(data)
        self.name = name


def create_job(job_type: str, filename: str) -> str:
    from django.core.cache import cache

    job_id = str(uuid.uuid4())
    job = {
        "id":          job_id,
        "type":        job_type,
        "type_label":  JOB_TYPE_LABELS.get(job_type, job_type),
        "filename":    filename,
        "status":      "queued",
        "started_at":  _now_iso(),
        "finished_at": None,
        "processed":   0,
        "total":       0,
        "result":      None,
        "error":       None,
    }
    cache.set(_jkey(job_id), job, _JOB_TTL)

    with _lock:
        index = cache.get(_INDEX_KEY) or []
        index.append({"id": job_id, "started_at": job["started_at"]})
        if len(index) > _MAX_JOBS:
            index = index[-_MAX_JOBS:]
        cache.set(_INDEX_KEY, index, _JOB_TTL)

    return job_id


def update_job(job_id: str, **kwargs) -> None:
    from django.core.cache import cache

    with _lock:
        job = cache.get(_jkey(job_id))
        if job:
            job.update(kwargs)
            cache.set(_jkey(job_id), job, _JOB_TTL)


def get_job(job_id: str) -> dict:
    from django.core.cache import cache

    return cache.get(_jkey(job_id)) or {}


def get_recent_jobs(limit: int = 20) -> list:
    from django.core.cache import cache

    index = cache.get(_INDEX_KEY) or []
    sorted_index = sorted(index, key=lambda x: x["started_at"], reverse=True)[:limit]
    jobs = [cache.get(_jkey(x["id"])) for x in sorted_index]
    jobs = [j for j in jobs if j]  # filter expired / missing entries

    # Auto-fail jobs stuck in running/queued for > 30 min (gunicorn restart mid-upload)
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(timespec="seconds")
    for j in jobs:
        if j.get("status") in ("running", "queued") and j.get("started_at", "") < stale_cutoff:
            update_job(j["id"], status="error", finished_at=_now_iso(),
                       error="Auto-failed: job stale (process likely restarted)")
            j["status"] = "error"  # reflect in this response too

    return jobs


def is_type_running(job_type: str) -> bool:
    """Return True if a non-stale job of this type is already queued or running."""
    from django.core.cache import cache

    stale_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(timespec="seconds")
    index = cache.get(_INDEX_KEY) or []
    for entry in index:
        job = cache.get(_jkey(entry["id"]))
        if not job:
            continue
        if job.get("type") != job_type:
            continue
        if job.get("status") not in ("queued", "running"):
            continue
        # Treat jobs stuck > 30 min as stale — do not block new uploads
        if job.get("started_at", "") < stale_cutoff:
            update_job(job["id"], status="error", finished_at=_now_iso(),
                       error="Auto-failed: job stale (process likely restarted)")
            continue
        return True
    return False


def make_progress_fn(job_id: str):
    """Return a callback: progress_fn(processed, total) → updates job in cache."""
    def _fn(processed: int, total: int):
        update_job(job_id, processed=processed, total=total)
    return _fn

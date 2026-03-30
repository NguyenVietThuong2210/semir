"""
App/cache_utils.py — Shared cache helpers.

Single source of truth for:
  • version-based invalidation  (bump_version / make_key)
  • thundering-herd protection   (get_or_compute)

Usage pattern
─────────────
  VER_KEY = "my_ver"            # one per domain (analytics / coupon / cnv)

  # Build a versioned key (embeds current version):
  key = make_key("my_ns", VER_KEY, param1, param2)

  # Compute once, cache result:
  data = get_or_compute(key, lambda: expensive_fn(), ttl=600)

  # Invalidate (all old keys become unreachable, expire naturally):
  bump_version(VER_KEY)
"""
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

_VER_TTL  = 86400 * 30  # 30 days  — version keys survive long idle periods
_DATA_TTL = 600          # 10 min   — default for computed analytics data


# ── version helpers ────────────────────────────────────────────────────────────

def make_key(namespace: str, ver_key: str, *parts) -> str:
    """Return a versioned cache key that encodes the current invalidation version."""
    v = cache.get(ver_key, 0)
    return f"{namespace}:{v}:" + ":".join(str(p) for p in parts)


def bump_version(ver_key: str) -> None:
    """
    Invalidate all cached data stored under ver_key by incrementing its version.
    Old keys become unreachable immediately; they expire naturally after their TTL.
    Safe to call from any process / worker.
    """
    v = cache.get(ver_key, 0)
    new_v = v + 1
    cache.set(ver_key, new_v, _VER_TTL)
    logger.info("cache invalidated: %s  ver %d → %d", ver_key, v, new_v)


# ── compute-once helper ────────────────────────────────────────────────────────

def get_or_compute(cache_key: str, compute_fn, ttl: int = _DATA_TTL):
    """
    Return cached value, or compute it exactly once per key.

    Thundering-herd protection
    ──────────────────────────
    cache.add() is atomic in both Redis and LocMemCache: it sets the key only if
    it did not already exist.  The first worker to call get_or_compute on a
    cache-miss acquires a lock key and computes.  Any other worker that arrives
    on the same cache miss while the first is computing will also call compute_fn
    (we cannot afford to block-wait with only 3 sync gunicorn workers), but only
    the first worker writes the result to cache.  This prevents write-storms while
    still letting each worker make progress.

    Returns
    ───────
    The computed (or cached) value, or None if compute_fn returns None/empty.
    """
    data = cache.get(cache_key)
    if data is not None:
        logger.debug("cache HIT  %s", cache_key)
        return data

    lock_key = f"{cache_key}:lk"
    # cache.add() → True only if the key did NOT exist (atomic)
    acquired = cache.add(lock_key, 1, ttl + 60)

    try:
        logger.info("cache MISS %s (lock=%s)", cache_key, acquired)
        data = compute_fn()
        if acquired and data is not None:
            # Only the lock-holder writes to avoid redundant set() from other workers
            cache.set(cache_key, data, ttl)
    finally:
        if acquired:
            cache.delete(lock_key)

    return data

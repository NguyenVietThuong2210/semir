"""
App/cnv/rate_limit.py

Distributed rate limiter for CNV membership-fetch calls.

Why distributed (Redis-backed via Django cache) instead of an in-process
token bucket: the 2026-07-12 incident showed that a purely in-process limiter
is not enough — three gunicorn workers each running their own scheduler (pre
leader-election fix) each had their own 50 req/s budget, so the COMBINED rate
hit CNV's server at 150 req/s and triggered 429s. The single-leader fix closes
that specific hole for the scheduled cron sync, but the manual "sync points"
admin action (App/cnv/views.py sync_cnv_points) can run in ANY of the 3
gunicorn worker processes and, before this module existed, had NO rate limit
at all. A Redis-backed limiter shared by both call sites is the only way to
guarantee the combined call rate — cron + manual, across all processes —
stays under CNV's 100 req/s cap.
"""
import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# CNV's own bucket is 100 tokens/sec (see the 429 error body: "Capacity: 100
# tokens, Refill rate: 100 tokens/second"). Default well under that so a
# fixed-window boundary burst (worst case ~2x one window) still can't exceed
# CNV's bucket capacity.
DEFAULT_MEMBERSHIP_RATE_LIMIT = 50


class DistributedRateLimiter:
    """Fixed-window rate limiter backed by Django's cache (Redis in prod,
    LocMemCache in dev — both support atomic incr). Blocking: acquire() sleeps
    the calling thread until a slot in the current window is available.

    Shared across processes via the same cache backend + key, so ALL callers
    (scheduled sync, manual admin sync, any future caller) draw from one
    combined budget — closing the multi-process/multi-caller gap a purely
    in-process token bucket cannot cover.
    """

    def __init__(self, rate: float, key: str):
        self._rate = max(1, int(rate))
        self._key = key

    def acquire(self):
        from django.core.cache import cache
        while True:
            now = time.time()
            window = int(now)
            cache_key = f"{self._key}:{window}"
            cache.add(cache_key, 0, timeout=2)  # idempotent: ensure key exists
            count = cache.incr(cache_key)
            if count <= self._rate:
                return
            # Over budget for this window — wait for the next one to start.
            sleep_s = max(1 - (now - window), 0.01)
            time.sleep(sleep_s)


_membership_limiter = None


def get_membership_rate_limiter() -> DistributedRateLimiter:
    """Module-level singleton so every caller (cron sync, manual admin sync)
    shares the exact same distributed budget."""
    global _membership_limiter
    if _membership_limiter is None:
        rate = getattr(settings, "CNV_MEMBERSHIP_RATE_LIMIT", DEFAULT_MEMBERSHIP_RATE_LIMIT)
        _membership_limiter = DistributedRateLimiter(rate, key="cnv_membership_rl")
        logger.info("CNV membership rate limiter initialized: %s req/s (shared, distributed)", rate)
    return _membership_limiter

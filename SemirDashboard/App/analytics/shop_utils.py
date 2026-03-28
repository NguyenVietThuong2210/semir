"""
App/analytics/shop_utils.py

Shop name normalization utility.

Usage:
    from App.analytics.shop_utils import get_shop_map, normalize_shop

    shop_map = get_shop_map()          # call once per request / computation
    title_id, display = normalize_shop("巴拉越南河内市…", shop_map)

If the raw name has no alias mapping, returns (None, raw_name) so existing
code that falls back to the raw string continues to work correctly.
"""
import time
import threading
import logging

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache = {"data": None, "ts": 0}
_TTL = 300  # 5 minutes — refresh after alias edits


def _build_map():
    """Build alias→(title_id, title_display) dict from DB."""
    from App.models import ShopNameAlias
    m = {}
    for a in ShopNameAlias.objects.select_related("title").all():
        m[a.alias.strip()] = (a.title_id, a.title.title)
    return m


def get_shop_map():
    """
    Return the alias→(title_id, display_title) dict, cached for _TTL seconds.
    Thread-safe.
    """
    now = time.time()
    with _lock:
        if _cache["data"] is None or (now - _cache["ts"]) > _TTL:
            try:
                _cache["data"] = _build_map()
                _cache["ts"] = now
                logger.debug("shop_map rebuilt (%d aliases)", len(_cache["data"]))
            except Exception:
                # DB not ready (e.g. migrations running) — return empty map
                logger.exception("shop_map build failed, returning empty map")
                return {}
        return _cache["data"]


def invalidate_shop_map():
    """Force next get_shop_map() call to rebuild from DB."""
    with _lock:
        _cache["data"] = None
        _cache["ts"] = 0


def normalize_shop(raw_name, shop_map=None):
    """
    Map a raw shop name string to (title_id, display_title).

    Returns:
        (int, str)  — (ShopNameTitle.id, canonical display title) if alias found
        (None, str) — (None, raw_name.strip()) if not mapped
    """
    if shop_map is None:
        shop_map = get_shop_map()
    raw = (raw_name or "").strip()
    if raw in shop_map:
        return shop_map[raw]
    return (None, raw or "Unknown")


def normalize_shop_display(raw_name, shop_map=None):
    """Convenience: return only the display title string."""
    _, display = normalize_shop(raw_name, shop_map)
    return display

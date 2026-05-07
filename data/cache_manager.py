"""
On-disk cache for yfinance payloads using joblib.

We deliberately keep the cache simple: one pickle per (ticker, kind)
pair, with a TTL stamped into the filename's mtime. This avoids
hammering yfinance during a sidebar tweak / rerun cycle.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import joblib

from config.settings import CACHE_DIR
from utils.logger import get_logger

log = get_logger("cache")

# Default TTL — long enough to survive sidebar reruns but short enough
# that an overnight scan still gets fresh data. yfinance is delayed
# anyway, so an hour or two does not change the answer.
DEFAULT_TTL_SECONDS: int = 60 * 60 * 6  # 6h


def _cache_path(key: str) -> Path:
    safe = key.replace("/", "_").replace("\\", "_").replace(":", "_")
    return CACHE_DIR / f"{safe}.joblib"


def cache_get(key: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Any | None:
    """Return cached payload for ``key`` if fresh, else ``None``."""
    path = _cache_path(key)
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > ttl_seconds:
        return None
    try:
        return joblib.load(path)
    except Exception as exc:  # corrupted cache entries should not crash analysis
        log.warning("Cache read failed for %s: %s", key, exc)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def cache_set(key: str, value: Any) -> None:
    """Persist ``value`` under ``key``."""
    path = _cache_path(key)
    try:
        joblib.dump(value, path, compress=3)
    except Exception as exc:
        log.warning("Cache write failed for %s: %s", key, exc)


def clear_cache() -> int:
    """Remove every cached payload. Returns count of deleted files."""
    n = 0
    for f in CACHE_DIR.glob("*.joblib"):
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    log.info("Cleared %d cache files", n)
    return n

"""
Robust, parallel yfinance fetcher with on-disk caching.

We fetch two payloads per ticker:

* ``history``  — OHLCV daily prices
* ``info``     — fundamentals snapshot (PE, ROE, debt, etc.)

Failures are isolated per ticker so one bad symbol cannot poison a
full scan. All payloads are cached, so a rerun within the TTL costs
nothing in network time.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Iterable

import pandas as pd
import yfinance as yf

from config.settings import (
    DEFAULT_HISTORY_INTERVAL,
    DEFAULT_HISTORY_PERIOD,
    FETCH_MAX_WORKERS,
)
from data.cache_manager import cache_get, cache_set
from utils.logger import get_logger

log = get_logger("fetcher")


# ----------------------------------------------------------------------
# Data containers
# ----------------------------------------------------------------------
@dataclass
class StockData:
    """Bundle of everything we know about a ticker."""
    ticker: str
    history: pd.DataFrame = field(default_factory=pd.DataFrame)
    info: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.history.empty


# ----------------------------------------------------------------------
# Single-ticker fetch
# ----------------------------------------------------------------------
def _fetch_history(ticker: str, period: str, interval: str) -> pd.DataFrame:
    cache_key = f"hist_{ticker}_{period}_{interval}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
            threads=False,
        )
    except Exception as exc:
        log.warning("history download failed for %s: %s", ticker, exc)
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    # yfinance sometimes returns a MultiIndex column even for a single
    # ticker — flatten that so downstream code can rely on simple names.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns=str.title)
    df.index = pd.to_datetime(df.index)
    df = df.dropna(how="all")
    cache_set(cache_key, df)
    return df


def _fetch_info(ticker: str) -> dict:
    cache_key = f"info_{ticker}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    info: dict = {}
    try:
        tk = yf.Ticker(ticker)
        # yfinance has unstable info endpoints; try in order of reliability.
        try:
            info = dict(tk.get_info())
        except Exception:
            try:
                info = dict(tk.info)
            except Exception:
                info = {}
        if not info:
            try:
                fast = tk.fast_info
                info = {
                    "marketCap": getattr(fast, "market_cap", None),
                    "currency": getattr(fast, "currency", None),
                    "shortName": ticker,
                }
            except Exception:
                info = {"shortName": ticker}
    except Exception as exc:
        log.warning("info fetch failed for %s: %s", ticker, exc)
        info = {"shortName": ticker}

    cache_set(cache_key, info)
    return info


def fetch_one(
    ticker: str,
    period: str = DEFAULT_HISTORY_PERIOD,
    interval: str = DEFAULT_HISTORY_INTERVAL,
) -> StockData:
    """Fetch full bundle for a single ticker."""
    try:
        history = _fetch_history(ticker, period, interval)
        info = _fetch_info(ticker)
        if history.empty:
            return StockData(ticker=ticker, history=history, info=info,
                             error="No price history returned.")
        return StockData(ticker=ticker, history=history, info=info)
    except Exception as exc:
        log.exception("unexpected fetch error for %s", ticker)
        return StockData(ticker=ticker, error=str(exc))


# ----------------------------------------------------------------------
# Bulk fetch
# ----------------------------------------------------------------------
def fetch_many(
    tickers: Iterable[str],
    period: str = DEFAULT_HISTORY_PERIOD,
    interval: str = DEFAULT_HISTORY_INTERVAL,
    max_workers: int = FETCH_MAX_WORKERS,
    progress_callback=None,
) -> list[StockData]:
    """Parallel fetch with isolated failures."""
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t and t.strip()))
    results: list[StockData] = []
    if not tickers:
        return results

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_one, t, period, interval): t for t in tickers}
        for i, fut in enumerate(as_completed(futures), start=1):
            try:
                results.append(fut.result())
            except Exception as exc:
                t = futures[fut]
                log.warning("worker error for %s: %s", t, exc)
                results.append(StockData(ticker=t, error=str(exc)))
            if progress_callback is not None:
                try:
                    progress_callback(i, len(tickers))
                except Exception:
                    pass

    # Preserve the input order for consistent UI tables.
    order = {t: i for i, t in enumerate(tickers)}
    results.sort(key=lambda r: order.get(r.ticker, 1_000_000))
    return results

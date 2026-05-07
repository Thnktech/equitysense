"""
Generic helper functions: numeric safety, formatting, and persistence.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from config.settings import EPS, SCORE_MAX, SCORE_MIN, WATCHLIST_FILE


# ----------------------------------------------------------------------
# Numerical helpers
# ----------------------------------------------------------------------
def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Divide numbers without raising on zero or NaN."""
    try:
        if denominator is None or math.isnan(denominator) or abs(denominator) < EPS:
            return default
        if numerator is None or math.isnan(numerator):
            return default
        return float(numerator) / float(denominator)
    except (TypeError, ValueError):
        return default


def clamp(value: float, lo: float = SCORE_MIN, hi: float = SCORE_MAX) -> float:
    """Constrain ``value`` into ``[lo, hi]``; NaNs collapse to ``lo``."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return lo
    return float(max(lo, min(hi, value)))


def normalize_series(series: pd.Series, lo: float = 0.0, hi: float = 100.0) -> pd.Series:
    """Min-max normalize a numeric series into a target range."""
    s = pd.to_numeric(series, errors="coerce")
    if s.dropna().empty:
        return pd.Series(np.full(len(series), (lo + hi) / 2.0), index=series.index)
    smin, smax = s.min(skipna=True), s.max(skipna=True)
    if smax - smin < EPS:
        return pd.Series(np.full(len(series), (lo + hi) / 2.0), index=series.index)
    scaled = (s - smin) / (smax - smin)
    return scaled * (hi - lo) + lo


def winsorize(series: pd.Series, lower: float = 0.02, upper: float = 0.98) -> pd.Series:
    """Cap extreme outliers at the given quantiles."""
    s = pd.to_numeric(series, errors="coerce")
    if s.dropna().empty:
        return s
    lo, hi = s.quantile(lower), s.quantile(upper)
    return s.clip(lower=lo, upper=hi)


# ----------------------------------------------------------------------
# Display helpers
# ----------------------------------------------------------------------
def format_currency(value: float | None, currency: str = "USD") -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    abs_v = abs(value)
    if abs_v >= 1e12:
        return f"{value/1e12:.2f}T {currency}"
    if abs_v >= 1e9:
        return f"{value/1e9:.2f}B {currency}"
    if abs_v >= 1e6:
        return f"{value/1e6:.2f}M {currency}"
    if abs_v >= 1e3:
        return f"{value/1e3:.2f}K {currency}"
    return f"{value:.2f} {currency}"


def format_percent(value: float | None, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{value*100:.{digits}f}%"


def format_score(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{value:.1f}"


def chunked(iterable: Iterable[Any], size: int) -> Iterable[list[Any]]:
    """Split an iterable into lists of length ``size``."""
    bucket: list[Any] = []
    for item in iterable:
        bucket.append(item)
        if len(bucket) >= size:
            yield bucket
            bucket = []
    if bucket:
        yield bucket


# ----------------------------------------------------------------------
# Watchlist helpers — thin wrappers around the session portfolio store.
# Kept only for backwards compatibility with older callers.
# ----------------------------------------------------------------------
def load_watchlist() -> list[str]:
    from data.portfolio import portfolio_tickers
    return portfolio_tickers()


def add_to_watchlist(ticker: str) -> list[str]:
    from data.portfolio import (
        Holding,
        add_or_update_holding,
        portfolio_tickers,
    )
    add_or_update_holding(Holding(ticker=ticker))
    return portfolio_tickers()


def remove_from_watchlist(ticker: str) -> list[str]:
    from data.portfolio import portfolio_tickers, remove_holding
    remove_holding(ticker)
    return portfolio_tickers()

"""
Signal-processing primitives used across the scoring engines.

Treating a price series as a noisy signal lets us re-use the same
toolkit a controls or DSP engineer would reach for: smoothing,
detrending, slope estimation, SNR.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

from config.settings import EPS


# ----------------------------------------------------------------------
# Smoothing / filtering
# ----------------------------------------------------------------------
def rolling_smooth(series: pd.Series, window: int = 21) -> pd.Series:
    """Centered rolling mean — a low-pass filter for the price signal."""
    s = pd.to_numeric(series, errors="coerce")
    if s.dropna().empty:
        return s
    window = max(3, min(window, max(3, len(s) // 4)))
    return s.rolling(window=window, min_periods=max(2, window // 2),
                     center=True).mean()


def savgol_smooth(series: pd.Series, window: int = 21, poly: int = 3) -> pd.Series:
    """Savitzky–Golay filter — preserves local maxima better than a
    moving average. Falls back to rolling_smooth when the series is short."""
    s = pd.to_numeric(series, errors="coerce").interpolate(limit_direction="both")
    if s.dropna().empty or len(s.dropna()) < window + 1:
        return rolling_smooth(series, window=window)
    if window % 2 == 0:  # window must be odd for savgol
        window += 1
    poly = min(poly, window - 1)
    try:
        smoothed = savgol_filter(s.values, window_length=window, polyorder=poly,
                                 mode="interp")
        return pd.Series(smoothed, index=s.index)
    except Exception:
        return rolling_smooth(series, window=window)


# ----------------------------------------------------------------------
# Returns / volatility
# ----------------------------------------------------------------------
def daily_returns(prices: pd.Series) -> pd.Series:
    return pd.to_numeric(prices, errors="coerce").pct_change().dropna()


def log_returns(prices: pd.Series) -> pd.Series:
    s = pd.to_numeric(prices, errors="coerce")
    return np.log(s / s.shift(1)).dropna()


def rolling_volatility(prices: pd.Series, window: int = 21) -> pd.Series:
    """Annualized rolling stddev of daily returns."""
    rets = daily_returns(prices)
    vol = rets.rolling(window=window, min_periods=max(5, window // 2)).std()
    return vol * np.sqrt(252)


# ----------------------------------------------------------------------
# Trend / slope
# ----------------------------------------------------------------------
def trend_slope(prices: pd.Series, window: int = 60) -> pd.Series:
    """Rolling linear-fit slope normalized by current price.

    A positive slope means the smoothed trend is moving up; the
    magnitude is dimensionless (% per day) so it is comparable across
    tickers and price levels.
    """
    s = pd.to_numeric(prices, errors="coerce").interpolate(limit_direction="both")
    if s.dropna().empty:
        return pd.Series(dtype=float, index=prices.index)

    x = np.arange(window, dtype=float)
    x_centered = x - x.mean()
    denom = (x_centered ** 2).sum() + EPS

    def _slope(values: np.ndarray) -> float:
        if len(values) < window or np.isnan(values).any():
            return np.nan
        y = values - values.mean()
        slope = (x_centered * y).sum() / denom
        last = values[-1] if values[-1] != 0 else EPS
        return slope / last

    return s.rolling(window=window).apply(_slope, raw=True)


def overall_trend_slope(prices: pd.Series) -> float:
    """Single-number slope across the whole window (annualized)."""
    s = pd.to_numeric(prices, errors="coerce").dropna()
    if len(s) < 20:
        return 0.0
    x = np.arange(len(s), dtype=float)
    x -= x.mean()
    y = s.values - s.values.mean()
    denom = (x ** 2).sum() + EPS
    slope = (x * y).sum() / denom
    last = float(s.iloc[-1]) if s.iloc[-1] != 0 else EPS
    return float(slope / last) * 252  # annualized


# ----------------------------------------------------------------------
# Drawdowns
# ----------------------------------------------------------------------
def drawdown_curve(prices: pd.Series) -> pd.Series:
    """Drawdown as a fraction of running peak (always <= 0)."""
    s = pd.to_numeric(prices, errors="coerce").dropna()
    if s.empty:
        return s
    running_max = s.cummax()
    return (s / running_max) - 1.0


def max_drawdown(prices: pd.Series) -> float:
    dd = drawdown_curve(prices)
    if dd.empty:
        return 0.0
    return float(dd.min())


def average_recovery_days(prices: pd.Series, threshold: float = -0.05) -> float:
    """Average number of days to recover from drawdowns deeper than ``threshold``.

    Returns +inf if the stock has not recovered yet.
    """
    s = pd.to_numeric(prices, errors="coerce").dropna()
    if s.empty:
        return float("nan")

    running_max = s.cummax()
    dd = (s / running_max) - 1.0

    in_drawdown = False
    start_idx = 0
    peak = 0.0
    durations: list[int] = []

    for i, (val, peak_val, dd_val) in enumerate(zip(s.values, running_max.values, dd.values)):
        if not in_drawdown and dd_val <= threshold:
            in_drawdown = True
            start_idx = i
            peak = peak_val
        elif in_drawdown and val >= peak:
            durations.append(i - start_idx)
            in_drawdown = False

    if not durations:
        return float("nan")
    return float(np.mean(durations))


# ----------------------------------------------------------------------
# Signal-to-noise
# ----------------------------------------------------------------------
def signal_to_noise(prices: pd.Series, smooth_window: int = 21) -> float:
    """Ratio of trend energy to residual energy.

    Higher = cleaner uptrend / downtrend; lower = choppy / noisy.
    Reported on a 0–10 scale (clipped) for downstream scoring.
    """
    s = pd.to_numeric(prices, errors="coerce").dropna()
    if len(s) < smooth_window * 2:
        return 0.0
    smoothed = savgol_smooth(s, window=smooth_window).reindex(s.index).bfill().ffill()
    residual = s - smoothed
    sig_power = float((smoothed - smoothed.mean()).pow(2).mean())
    noise_power = float(residual.pow(2).mean()) + EPS
    snr = sig_power / noise_power
    return float(np.clip(snr, 0.0, 10.0))


# ----------------------------------------------------------------------
# Momentum quality
# ----------------------------------------------------------------------
def momentum_consistency(prices: pd.Series, window: int = 63) -> float:
    """Fraction of days where the smoothed trend ticks in the same direction.

    1.0 = perfectly monotonic; 0.5 = random walk.
    """
    s = pd.to_numeric(prices, errors="coerce").dropna()
    if len(s) < window + 5:
        return 0.5
    smoothed = rolling_smooth(s, window=max(5, window // 5))
    diffs = smoothed.diff().dropna().tail(window)
    if diffs.empty:
        return 0.5
    pos = (diffs > 0).sum()
    neg = (diffs < 0).sum()
    total = max(1, pos + neg)
    return float(max(pos, neg) / total)

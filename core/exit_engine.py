"""
Exit-warning engine.

Looks at price action + fundamentals + computed scores and emits a
list of plain-English warnings when something is deteriorating.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.scoring_engine import StockScore
from core.signal_processing import (
    daily_returns,
    drawdown_curve,
    overall_trend_slope,
    rolling_volatility,
)
from data.yfinance_fetcher import StockData


@dataclass
class ExitWarning:
    severity: str   # "low" | "medium" | "high"
    label: str
    message: str


def _last_or(series: pd.Series, fallback: float = 0.0) -> float:
    s = series.dropna()
    return float(s.iloc[-1]) if not s.empty else fallback


def evaluate_exit(bundle: StockData, score: StockScore) -> list[ExitWarning]:
    """Return ordered list of warnings (most severe first)."""
    warnings: list[ExitWarning] = []
    if bundle is None or not bundle.ok or bundle.history.empty:
        return warnings

    close = bundle.history["Close"].astype(float)

    # 1. Trend breakdown
    slope = overall_trend_slope(close)
    if slope < -0.10:
        warnings.append(ExitWarning(
            "high", "Trend Breakdown",
            f"Annualized trend slope is {slope*100:.1f}%/yr — clear downtrend."))
    elif slope < 0.0:
        warnings.append(ExitWarning(
            "medium", "Trend Weakening",
            f"Trend slope turned slightly negative ({slope*100:.1f}%/yr)."))

    # 2. Drawdown acceleration
    dd = drawdown_curve(close)
    last_dd = _last_or(dd, 0.0)
    if last_dd <= -0.25:
        warnings.append(ExitWarning(
            "high", "Deep Drawdown",
            f"Currently {last_dd*100:.1f}% below the recent peak."))
    elif last_dd <= -0.10:
        warnings.append(ExitWarning(
            "medium", "Drawdown Building",
            f"Now {last_dd*100:.1f}% off peak."))

    # 3. Volatility spike
    vol = rolling_volatility(close, window=21).dropna()
    if not vol.empty:
        recent = float(vol.tail(21).mean())
        long_run = float(vol.tail(252).mean()) if len(vol) >= 60 else recent
        if recent > 0.5 and recent > long_run * 1.3:
            warnings.append(ExitWarning(
                "high", "Volatility Spike",
                f"21d vol = {recent*100:.0f}%, vs long-run {long_run*100:.0f}%."))
        elif recent > long_run * 1.2:
            warnings.append(ExitWarning(
                "medium", "Volatility Elevated",
                f"21d vol = {recent*100:.0f}%, above its long-run baseline."))

    # 4. Momentum loss
    if score.momentum_quality < 35:
        warnings.append(ExitWarning(
            "medium", "Momentum Loss",
            f"Momentum quality only {score.momentum_quality:.0f}/100."))

    # 5. Earnings instability
    if score.stability.get("EST", 100.0) < 35:
        warnings.append(ExitWarning(
            "medium", "Earnings Instability",
            "Earnings settling-time score is poor — recent shocks haven't dampened out."))

    # 6. Valuation risk
    if score.valuation_status == "Expensive":
        warnings.append(ExitWarning(
            "low", "Valuation Stretched",
            "Multiples sit above their healthy range."))

    # 7. Profitability deterioration
    info = bundle.info or {}
    profit_margin = info.get("profitMargins")
    if profit_margin is not None and profit_margin < 0:
        warnings.append(ExitWarning(
            "high", "Negative Margins",
            f"Profit margin = {profit_margin*100:.1f}% — company is loss-making."))

    # 8. Recent crash
    rets = daily_returns(close).tail(5)
    if not rets.empty and rets.sum() < -0.10:
        warnings.append(ExitWarning(
            "high", "Sharp Recent Decline",
            f"Down {rets.sum()*100:.1f}% in the last 5 sessions."))

    # Sort by severity rank
    rank = {"high": 0, "medium": 1, "low": 2}
    warnings.sort(key=lambda w: rank.get(w.severity, 9))
    return warnings


def summarize_warnings(warnings: list[ExitWarning]) -> str:
    if not warnings:
        return "No active exit warnings."
    counts = {"high": 0, "medium": 0, "low": 0}
    for w in warnings:
        counts[w.severity] = counts.get(w.severity, 0) + 1
    parts = [f"{v} {k}" for k, v in counts.items() if v]
    return "Warnings: " + ", ".join(parts)

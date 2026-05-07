"""
Scoring engine.

Takes a fully-fetched ``StockData`` bundle and produces:

* Per-factor 0..100 scores (eight of them)
* A weighted final score, given the user's mode/style/risk/horizon
* The engineering-style "stability metrics" used by the explainer

The scoring is deterministic — no randomness, no ML model — so the
explainability surface is just the factor-by-factor breakdown.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core.factor_weights import FACTORS, get_weights
from core.signal_processing import (
    daily_returns,
    max_drawdown,
    momentum_consistency,
    overall_trend_slope,
    rolling_volatility,
)
from core.stability_metrics import compute_stability_metrics
from data.yfinance_fetcher import StockData
from utils.helpers import clamp, safe_div


# ----------------------------------------------------------------------
# Result container
# ----------------------------------------------------------------------
@dataclass
class StockScore:
    ticker: str
    company: str = ""
    sector: str = ""
    region: str = ""
    currency: str = "USD"
    price: float = float("nan")
    market_cap: float = float("nan")

    factor_scores: dict[str, float] = field(default_factory=dict)
    stability: dict[str, float] = field(default_factory=dict)
    final_score: float = 0.0
    recommendation: str = "HOLD"
    exit_risk: float = 0.0
    valuation_status: str = "Fair"
    momentum_quality: float = 50.0
    raw_metrics: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    def to_row(self) -> dict:
        return {
            "Ticker": self.ticker,
            "Company": self.company,
            "Sector": self.sector,
            "Region": self.region,
            "Price": self.price,
            "Final Score": round(self.final_score, 1),
            "Stability Score": round(self.factor_scores.get("stability", 0.0), 1),
            "Exit Risk": round(self.exit_risk, 1),
            "Momentum Quality": round(self.momentum_quality, 1),
            "Valuation": self.valuation_status,
            "Recommendation": self.recommendation,
            "Market Cap": self.market_cap,
            "Currency": self.currency,
        }


# ----------------------------------------------------------------------
# Per-factor scorers (each returns a 0..100 score)
# ----------------------------------------------------------------------
def _fundamentals_score(info: dict, stability: dict) -> float:
    if not info:
        return stability.get("FSS", 50.0)
    fss = stability.get("FSS", 50.0)
    roe = (info.get("returnOnEquity") or 0.0) * 100.0
    roe_term = clamp((roe / 25.0) * 100.0)
    debt = info.get("debtToEquity")
    debt_term = clamp(100.0 - (float(debt) / 2.0)) if debt is not None else 50.0
    return clamp(0.5 * fss + 0.3 * roe_term + 0.2 * debt_term)


def _stability_score(stability: dict) -> float:
    return clamp((stability.get("DDR", 50.0) + stability.get("EST", 50.0)) / 2.0)


def _trend_quality_score(history: pd.DataFrame) -> float:
    if history is None or history.empty:
        return 50.0
    close = history["Close"].astype(float)
    slope = overall_trend_slope(close)         # annualized fractional slope
    consistency = momentum_consistency(close, window=126)
    # 30% annualized return is a great trend, -30% is very poor.
    slope_term = clamp(((slope + 0.30) / 0.60) * 100.0)
    cons_term = clamp(consistency * 100.0)
    return clamp(0.6 * slope_term + 0.4 * cons_term)


def _momentum_score(history: pd.DataFrame) -> float:
    if history is None or history.empty:
        return 50.0
    close = history["Close"].astype(float)
    if len(close) < 30:
        return 50.0
    last = float(close.iloc[-1])
    ret_1m = safe_div(last - float(close.iloc[-min(21, len(close))]),
                      float(close.iloc[-min(21, len(close))]))
    ret_3m = safe_div(last - float(close.iloc[-min(63, len(close))]),
                      float(close.iloc[-min(63, len(close))]))
    ret_6m = safe_div(last - float(close.iloc[-min(126, len(close))]),
                      float(close.iloc[-min(126, len(close))]))
    blended = 0.5 * ret_1m + 0.3 * ret_3m + 0.2 * ret_6m
    # +40% blended = top score, -20% = floor
    return clamp(((blended + 0.20) / 0.60) * 100.0)


def _risk_score(history: pd.DataFrame) -> float:
    """Higher = SAFER (lower realized risk)."""
    if history is None or history.empty:
        return 50.0
    close = history["Close"].astype(float)
    vol = rolling_volatility(close, window=21).dropna()
    last_vol = float(vol.tail(20).mean()) if not vol.empty else 0.4
    vol_term = clamp((1.0 - (last_vol / 0.60)) * 100.0)
    mdd = abs(max_drawdown(close))
    mdd_term = clamp((1.0 - (mdd / 0.60)) * 100.0)
    return clamp(0.5 * vol_term + 0.5 * mdd_term)


def _valuation_score(info: dict) -> tuple[float, str]:
    """Higher = cheaper. Also returns a categorical 'Cheap/Fair/Expensive'."""
    if not info:
        return 50.0, "Unknown"
    pe = info.get("trailingPE") or info.get("forwardPE")
    pb = info.get("priceToBook")
    ps = info.get("priceToSalesTrailing12Months")

    parts: list[float] = []
    if pe is not None and pe > 0:
        parts.append(clamp((1.0 - min(float(pe) / 50.0, 1.0)) * 100.0))
    if pb is not None and pb > 0:
        parts.append(clamp((1.0 - min(float(pb) / 8.0, 1.0)) * 100.0))
    if ps is not None and ps > 0:
        parts.append(clamp((1.0 - min(float(ps) / 10.0, 1.0)) * 100.0))

    score = float(np.mean(parts)) if parts else 50.0
    if score > 65:
        label = "Cheap"
    elif score < 35:
        label = "Expensive"
    else:
        label = "Fair"
    return clamp(score), label


def _growth_score(info: dict) -> float:
    if not info:
        return 50.0
    eg = info.get("earningsQuarterlyGrowth") or info.get("earningsGrowth") or 0.0
    rg = info.get("revenueGrowth") or 0.0
    eg_term = clamp(((float(eg) + 0.20) / 0.60) * 100.0)
    rg_term = clamp(((float(rg) + 0.05) / 0.40) * 100.0)
    return clamp(0.55 * eg_term + 0.45 * rg_term)


def _confidence_score(stability: dict) -> float:
    return clamp((stability.get("PCS", 50.0) + stability.get("SNIR", 50.0)) / 2.0)


# ----------------------------------------------------------------------
# Recommendation logic
# ----------------------------------------------------------------------
def _classify(final_score: float, mode: str) -> str:
    """Translate a final score into BUY/HOLD/SELL/AVOID/etc."""
    mode = mode.upper()
    if mode == "BUY":
        if final_score >= 75:
            return "STRONG BUY"
        if final_score >= 60:
            return "BUY"
        if final_score >= 45:
            return "HOLD"
        if final_score >= 30:
            return "AVOID"
        return "STRONG AVOID"
    # SELL mode: high score = strong sell signal (i.e. high exit pressure)
    if final_score >= 75:
        return "STRONG SELL"
    if final_score >= 60:
        return "SELL"
    if final_score >= 45:
        return "TRIM"
    if final_score >= 30:
        return "HOLD"
    return "KEEP"


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def score_stock(
    bundle: StockData,
    mode: str = "BUY",
    style: str = "Hybrid Engineering Mode",
    risk: str = "Moderate",
    horizon: str = "Months",
) -> StockScore:
    """Score a single stock end-to-end."""
    score = StockScore(ticker=bundle.ticker)
    info = bundle.info or {}

    score.company = info.get("longName") or info.get("shortName") or bundle.ticker
    score.sector = info.get("sector") or "—"
    score.currency = info.get("currency") or "USD"
    score.market_cap = float(info.get("marketCap") or float("nan"))

    if not bundle.ok:
        score.error = bundle.error or "no data"
        score.recommendation = "NO DATA"
        return score

    history = bundle.history
    score.price = float(history["Close"].iloc[-1])

    stability = compute_stability_metrics(history, info)
    score.stability = stability

    fundamentals = _fundamentals_score(info, stability)
    stab = _stability_score(stability)
    trend = _trend_quality_score(history)
    momentum = _momentum_score(history)
    risk_safety = _risk_score(history)
    valuation, val_label = _valuation_score(info)
    growth = _growth_score(info)
    confidence = _confidence_score(stability)

    factor_scores = {
        "fundamentals": fundamentals,
        "stability": stab,
        "trend_quality": trend,
        "momentum": momentum,
        "risk": risk_safety,
        "valuation": valuation,
        "growth": growth,
        "confidence": confidence,
    }
    score.factor_scores = factor_scores
    score.valuation_status = val_label
    score.momentum_quality = (momentum + trend) / 2.0

    # ----- weighted fusion -----
    weights = get_weights(mode=mode, style=style, risk=risk, horizon=horizon)
    if mode.upper() == "BUY":
        # BUY mode: high factor scores -> high final score
        final = sum(weights[f] * factor_scores[f] for f in FACTORS)
    else:
        # SELL mode: invert the "good" factors so they become exit pressure
        invert = {"fundamentals", "stability", "trend_quality",
                  "momentum", "valuation", "growth", "confidence"}
        final = 0.0
        for f in FACTORS:
            v = factor_scores[f]
            if f in invert:
                v = 100.0 - v
            # Risk score is "higher = safer", invert it as well in SELL
            if f == "risk":
                v = 100.0 - v
            final += weights[f] * v

    score.final_score = clamp(final)
    score.recommendation = _classify(score.final_score, mode)

    # Exit risk: independent of mode, useful in BUY too
    score.exit_risk = clamp(
        0.4 * (100.0 - risk_safety)
        + 0.3 * (100.0 - stab)
        + 0.2 * (100.0 - momentum)
        + 0.1 * (100.0 - valuation)
    )

    # Useful raw numbers for the explainability/debug pane
    rets = daily_returns(history["Close"]).tail(252)
    score.raw_metrics = {
        "annualized_return": float(rets.mean() * 252) if not rets.empty else 0.0,
        "annualized_volatility": float(rets.std() * np.sqrt(252)) if not rets.empty else 0.0,
        "max_drawdown": float(max_drawdown(history["Close"])),
        "trend_slope": float(overall_trend_slope(history["Close"])),
        "momentum_consistency": float(momentum_consistency(history["Close"], window=126)),
    }

    return score


def score_many(
    bundles: list[StockData],
    mode: str = "BUY",
    style: str = "Hybrid Engineering Mode",
    risk: str = "Moderate",
    horizon: str = "Months",
) -> list[StockScore]:
    return [score_stock(b, mode, style, risk, horizon) for b in bundles]

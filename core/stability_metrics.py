"""
Engineering-inspired stability and resilience metrics.

The metrics here are deliberately scaled to 0-100 so they can be fused
linearly in the scoring engine. Each function is documented with the
control-system / DSP analogy that inspired it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import EPS
from core.signal_processing import (
    average_recovery_days,
    daily_returns,
    drawdown_curve,
    max_drawdown,
    momentum_consistency,
    rolling_volatility,
    signal_to_noise,
)
from utils.helpers import clamp, safe_div


# ----------------------------------------------------------------------
# Financial Stability Score (FSS)
# ----------------------------------------------------------------------
def financial_stability_score(info: dict) -> float:
    """Fundamental stability composite — analogous to a stability margin
    in control systems. Higher = the underlying business has more
    headroom before something breaks.

    Components (each 0..1, then averaged and rescaled):
      * margin consistency (operating + profit margins)
      * debt headroom (lower debt/equity = better)
      * cash flow positivity (free cash flow / market cap)
      * profitability (ROE)
    """
    if not info:
        return 50.0

    op_margin = info.get("operatingMargins") or 0.0
    profit_margin = info.get("profitMargins") or 0.0
    debt_to_equity = info.get("debtToEquity")
    fcf = info.get("freeCashflow") or 0.0
    market_cap = info.get("marketCap") or 0.0
    roe = info.get("returnOnEquity") or 0.0

    # Margins: 20% margin -> ~max score
    margin_term = clamp(((op_margin + profit_margin) / 2) / 0.20, 0.0, 1.0)

    # Debt: yfinance reports D/E in % (e.g. 60.0 = 60%). 0 -> 1.0, 200 -> 0.0
    if debt_to_equity is None:
        debt_term = 0.5
    else:
        debt_term = clamp(1.0 - (float(debt_to_equity) / 200.0), 0.0, 1.0)

    fcf_yield = safe_div(fcf, market_cap)
    fcf_term = clamp(fcf_yield / 0.08, 0.0, 1.0)  # 8% FCF yield is excellent

    roe_term = clamp(roe / 0.20, 0.0, 1.0)  # 20% ROE is excellent

    raw = 0.30 * margin_term + 0.25 * debt_term + 0.25 * fcf_term + 0.20 * roe_term
    return clamp(raw * 100.0)


# ----------------------------------------------------------------------
# Drawdown Damping Ratio (DDR)
# ----------------------------------------------------------------------
def drawdown_damping_ratio(prices: pd.Series) -> float:
    """How quickly does the price recover from drawdowns?

    Inspired by the damping ratio of a second-order system: a fast,
    well-damped response is rewarded, an undamped (slow) one is punished.
    """
    if prices is None or prices.empty:
        return 50.0

    mdd = abs(max_drawdown(prices))
    recovery = average_recovery_days(prices, threshold=-0.05)

    # Map max drawdown: 0% -> 1.0, 60%+ -> 0.0
    dd_term = clamp(1.0 - (mdd / 0.60), 0.0, 1.0)

    # Map recovery: 0..120d great, >500d poor
    if np.isnan(recovery) or np.isinf(recovery):
        rec_term = 0.5
    else:
        rec_term = clamp(1.0 - (recovery / 500.0), 0.0, 1.0)

    return clamp((0.5 * dd_term + 0.5 * rec_term) * 100.0)


# ----------------------------------------------------------------------
# Signal-to-Noise Investment Ratio (SNIR)
# ----------------------------------------------------------------------
def signal_to_noise_investment_ratio(prices: pd.Series) -> float:
    """SNR of the price signal, mapped onto 0..100."""
    snr = signal_to_noise(prices, smooth_window=21)
    return clamp((snr / 5.0) * 100.0)  # snr ~5 = excellent


# ----------------------------------------------------------------------
# Earnings Settling Time (EST)
# ----------------------------------------------------------------------
def earnings_settling_time(info: dict) -> float:
    """Proxy for how quickly earnings stabilize after a shock.

    yfinance does not expose a clean settling-time series, so we infer
    it from earnings growth + revenue growth + profit margin trajectory.
    Higher score = faster settling, more predictable earnings.
    """
    if not info:
        return 50.0

    earnings_growth = info.get("earningsQuarterlyGrowth") or 0.0
    revenue_growth = info.get("revenueGrowth") or 0.0
    profit_margin = info.get("profitMargins") or 0.0

    # Penalize deep negative growth (earnings still ringing).
    eg_term = clamp((earnings_growth + 0.20) / 0.40, 0.0, 1.0)
    rg_term = clamp((revenue_growth + 0.10) / 0.30, 0.0, 1.0)
    pm_term = clamp(profit_margin / 0.20, 0.0, 1.0)

    return clamp((0.45 * eg_term + 0.30 * rg_term + 0.25 * pm_term) * 100.0)


# ----------------------------------------------------------------------
# Predictive Confidence Score (PCS)
# ----------------------------------------------------------------------
def predictive_confidence_score(prices: pd.Series) -> float:
    """How predictable is the price evolution?

    Combines momentum consistency with low realized volatility.
    """
    if prices is None or prices.empty:
        return 50.0

    consistency = momentum_consistency(prices, window=126)
    vol = rolling_volatility(prices, window=21).dropna()
    last_vol = float(vol.tail(20).mean()) if not vol.empty else 0.4

    # 50% annualized vol -> ~0; 0% -> 1
    vol_term = clamp(1.0 - (last_vol / 0.50), 0.0, 1.0)

    return clamp((0.6 * consistency + 0.4 * vol_term) * 100.0)


# ----------------------------------------------------------------------
# Aggregator
# ----------------------------------------------------------------------
def compute_stability_metrics(history: pd.DataFrame, info: dict) -> dict[str, float]:
    """Compute the full set of engineering-style metrics for a ticker."""
    if history is None or history.empty or "Close" not in history.columns:
        return {
            "FSS": financial_stability_score(info or {}),
            "DDR": 50.0,
            "SNIR": 50.0,
            "EST": earnings_settling_time(info or {}),
            "PCS": 50.0,
        }

    close = history["Close"].astype(float)
    return {
        "FSS": financial_stability_score(info or {}),
        "DDR": drawdown_damping_ratio(close),
        "SNIR": signal_to_noise_investment_ratio(close),
        "EST": earnings_settling_time(info or {}),
        "PCS": predictive_confidence_score(close),
    }

"""
Dynamic factor weighting.

Each (mode, style, risk) tuple maps to a weight vector for the eight
factors the scoring engine evaluates. Weights are normalized to sum to
1.0 so the final score stays on a 0..100 scale.

Factors:
    fundamentals     — financial stability (FSS, valuation, profitability)
    stability        — DDR + earnings settling
    trend_quality    — slope, smoothness
    momentum         — recent momentum, persistence
    risk             — drawdown, volatility (penalty)
    valuation        — PE / PB / dividend (cheaper = better in BUY)
    growth           — revenue / earnings growth
    confidence       — PCS + SNIR
"""
from __future__ import annotations

FACTORS = [
    "fundamentals",
    "stability",
    "trend_quality",
    "momentum",
    "risk",
    "valuation",
    "growth",
    "confidence",
]


# ----------------------------------------------------------------------
# Style weights — opinions about which factors matter for each style.
# Each row is a partial weight that gets blended with risk and mode.
# ----------------------------------------------------------------------
STYLE_WEIGHTS: dict[str, dict[str, float]] = {
    "Long-Term Compounder": {
        "fundamentals": 0.25, "stability": 0.20, "trend_quality": 0.10,
        "momentum": 0.05, "risk": 0.10, "valuation": 0.10,
        "growth": 0.10, "confidence": 0.10,
    },
    "Value Investing": {
        "fundamentals": 0.20, "stability": 0.15, "trend_quality": 0.05,
        "momentum": 0.05, "risk": 0.10, "valuation": 0.30,
        "growth": 0.05, "confidence": 0.10,
    },
    "Growth Investing": {
        "fundamentals": 0.10, "stability": 0.10, "trend_quality": 0.15,
        "momentum": 0.15, "risk": 0.05, "valuation": 0.05,
        "growth": 0.30, "confidence": 0.10,
    },
    "Momentum Investing": {
        "fundamentals": 0.05, "stability": 0.05, "trend_quality": 0.20,
        "momentum": 0.30, "risk": 0.05, "valuation": 0.05,
        "growth": 0.15, "confidence": 0.15,
    },
    "Swing Trading": {
        "fundamentals": 0.05, "stability": 0.05, "trend_quality": 0.20,
        "momentum": 0.30, "risk": 0.10, "valuation": 0.05,
        "growth": 0.05, "confidence": 0.20,
    },
    "Defensive Investing": {
        "fundamentals": 0.20, "stability": 0.30, "trend_quality": 0.05,
        "momentum": 0.05, "risk": 0.20, "valuation": 0.10,
        "growth": 0.00, "confidence": 0.10,
    },
    "Dividend Investing": {
        "fundamentals": 0.25, "stability": 0.20, "trend_quality": 0.05,
        "momentum": 0.05, "risk": 0.10, "valuation": 0.20,
        "growth": 0.05, "confidence": 0.10,
    },
    "Hybrid Engineering Mode": {
        "fundamentals": 0.15, "stability": 0.15, "trend_quality": 0.15,
        "momentum": 0.10, "risk": 0.10, "valuation": 0.10,
        "growth": 0.10, "confidence": 0.15,
    },
}


# ----------------------------------------------------------------------
# Risk multipliers — applied per factor before renormalizing.
# Conservative shifts mass toward stability/risk; aggressive shifts
# toward momentum/growth.
# ----------------------------------------------------------------------
RISK_MULTIPLIERS: dict[str, dict[str, float]] = {
    "Conservative": {
        "fundamentals": 1.20, "stability": 1.40, "trend_quality": 1.00,
        "momentum": 0.70, "risk": 1.40, "valuation": 1.10,
        "growth": 0.70, "confidence": 1.20,
    },
    "Moderate": {
        "fundamentals": 1.00, "stability": 1.00, "trend_quality": 1.00,
        "momentum": 1.00, "risk": 1.00, "valuation": 1.00,
        "growth": 1.00, "confidence": 1.00,
    },
    "Aggressive": {
        "fundamentals": 0.80, "stability": 0.70, "trend_quality": 1.10,
        "momentum": 1.40, "risk": 0.70, "valuation": 0.90,
        "growth": 1.40, "confidence": 1.00,
    },
}


# ----------------------------------------------------------------------
# Holding-period nudges — short horizons emphasize momentum/quality;
# long horizons emphasize fundamentals/stability.
# ----------------------------------------------------------------------
HORIZON_MULTIPLIERS: dict[str, dict[str, float]] = {
    "Days": {
        "fundamentals": 0.50, "stability": 0.60, "momentum": 1.50,
        "trend_quality": 1.30, "confidence": 1.20,
    },
    "Weeks": {
        "fundamentals": 0.70, "stability": 0.80, "momentum": 1.30,
        "trend_quality": 1.20, "confidence": 1.10,
    },
    "Months": {
        "fundamentals": 1.00, "stability": 1.00, "momentum": 1.00,
        "trend_quality": 1.00, "confidence": 1.00,
    },
    "Years": {
        "fundamentals": 1.30, "stability": 1.30, "momentum": 0.70,
        "trend_quality": 0.90, "confidence": 1.00, "growth": 1.10,
    },
}


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, v) for v in weights.values())
    if total <= 0:
        equal = 1.0 / max(1, len(FACTORS))
        return {f: equal for f in FACTORS}
    return {k: max(0.0, v) / total for k, v in weights.items()}


def get_weights(
    mode: str = "BUY",
    style: str = "Hybrid Engineering Mode",
    risk: str = "Moderate",
    horizon: str = "Months",
) -> dict[str, float]:
    """Return final factor weights for the supplied user selections.

    In SELL mode the ``risk`` factor (drawdown / volatility) gets
    extra emphasis — we want to flag deteriorating positions early.
    """
    base = dict(STYLE_WEIGHTS.get(style, STYLE_WEIGHTS["Hybrid Engineering Mode"]))
    risk_mult = RISK_MULTIPLIERS.get(risk, RISK_MULTIPLIERS["Moderate"])
    horizon_mult = HORIZON_MULTIPLIERS.get(horizon, {})

    blended: dict[str, float] = {}
    for f in FACTORS:
        w = base.get(f, 0.0)
        w *= risk_mult.get(f, 1.0)
        w *= horizon_mult.get(f, 1.0)
        blended[f] = w

    if mode.upper() == "SELL":
        blended["risk"] *= 1.6
        blended["valuation"] *= 1.2
        blended["momentum"] *= 0.8

    return _normalize(blended)

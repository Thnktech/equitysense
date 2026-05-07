"""
Explainability layer.

Given a ``StockScore`` plus the user's current weights, produce a
human-readable breakdown showing how much each factor contributed
(positively or negatively) to the final score.

The contribution of factor ``f`` is defined as:

    contrib(f) = weight(f) * (score(f) - 50)

so that a factor scoring 50/100 contributes nothing, > 50 lifts the
final score, and < 50 drags it down.
"""
from __future__ import annotations

import pandas as pd

from core.factor_weights import FACTORS, get_weights
from core.scoring_engine import StockScore

FACTOR_LABELS: dict[str, str] = {
    "fundamentals": "Fundamentals (FSS, ROE, debt)",
    "stability": "Stability (DDR, settling time)",
    "trend_quality": "Trend Quality",
    "momentum": "Momentum",
    "risk": "Risk Damping",
    "valuation": "Valuation",
    "growth": "Growth",
    "confidence": "Predictive Confidence (PCS, SNIR)",
}


def build_contribution_table(
    score: StockScore,
    *,
    mode: str = "BUY",
    style: str = "Hybrid Engineering Mode",
    risk: str = "Moderate",
    horizon: str = "Months",
) -> pd.DataFrame:
    """Return a sorted contribution dataframe for a single stock."""
    if not score.factor_scores:
        return pd.DataFrame(columns=["Factor", "Score", "Weight", "Contribution"])

    weights = get_weights(mode=mode, style=style, risk=risk, horizon=horizon)
    rows = []
    for f in FACTORS:
        s = score.factor_scores.get(f, 50.0)
        if mode.upper() == "SELL":
            # Same inversion as in the scoring engine, so the chart
            # explains what the user actually sees.
            s_for_chart = 100.0 - s
        else:
            s_for_chart = s
        w = weights.get(f, 0.0)
        contrib = w * (s_for_chart - 50.0)
        rows.append({
            "Factor": FACTOR_LABELS.get(f, f),
            "FactorKey": f,
            "Score": round(s_for_chart, 1),
            "Weight": round(w * 100, 1),
            "Contribution": round(contrib, 2),
        })

    df = pd.DataFrame(rows)
    return df.sort_values("Contribution", ascending=False).reset_index(drop=True)


def narrative_summary(score: StockScore, mode: str = "BUY") -> str:
    """A short textual summary of why the stock scored what it did."""
    if score.error:
        return f"No data could be fetched: {score.error}"

    fs = score.factor_scores
    strengths = sorted(fs.items(), key=lambda kv: kv[1], reverse=True)[:3]
    weaknesses = sorted(fs.items(), key=lambda kv: kv[1])[:2]

    s_text = ", ".join(f"{FACTOR_LABELS.get(k,k)} ({v:.0f})" for k, v in strengths)
    w_text = ", ".join(f"{FACTOR_LABELS.get(k,k)} ({v:.0f})" for k, v in weaknesses)

    verdict = score.recommendation
    return (
        f"Final score {score.final_score:.1f}/100 — recommendation: {verdict}. "
        f"Strongest factors: {s_text}. Weakest factors: {w_text}. "
        f"Engineering metrics — FSS {score.stability.get('FSS', 0):.0f}, "
        f"DDR {score.stability.get('DDR', 0):.0f}, "
        f"SNIR {score.stability.get('SNIR', 0):.0f}, "
        f"EST {score.stability.get('EST', 0):.0f}, "
        f"PCS {score.stability.get('PCS', 0):.0f}."
    )

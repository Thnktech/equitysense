"""
"Top Picks" panel — the headline call-to-action above the main table.

In BUY mode it shows the highest-scoring stocks (best to BUY now).
In SELL mode it shows the highest-scoring stocks (highest exit
pressure — best to SELL now), since the SELL pipeline already
inverts the underlying factor scores.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd
import streamlit as st

from config.settings import COLORS
from core.scoring_engine import StockScore
from utils.helpers import format_currency, format_score


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _badge_color(rec: str) -> str:
    rec = (rec or "").upper()
    if "STRONG BUY" in rec or "STRONG SELL" in rec:
        return COLORS["positive"] if "BUY" in rec else COLORS["negative"]
    if "BUY" in rec:
        return COLORS["positive"]
    if "SELL" in rec:
        return COLORS["negative"]
    if "TRIM" in rec or "AVOID" in rec:
        return COLORS["warning"]
    return COLORS["muted"]


def _score_color(score: float) -> str:
    if score >= 75:
        return COLORS["positive"]
    if score >= 50:
        return COLORS["warning"]
    return COLORS["negative"]


def _short_reason(score: StockScore, mode: str) -> str:
    """One-line justification for the pick."""
    fs = score.factor_scores or {}
    if not fs:
        return ""
    if mode.upper() == "BUY":
        # Highlight the strongest contributing factor.
        best_key, best_val = max(fs.items(), key=lambda kv: kv[1])
        labels = {
            "fundamentals": "strong fundamentals",
            "stability": "high stability",
            "trend_quality": "clean uptrend",
            "momentum": "strong momentum",
            "risk": "low realized risk",
            "valuation": "attractive valuation",
            "growth": "strong growth",
            "confidence": "high predictive confidence",
        }
        return f"{labels.get(best_key, best_key)} ({best_val:.0f}/100)"
    # SELL mode: surface the worst (i.e. most-deteriorated) factor.
    worst_key, worst_val = min(fs.items(), key=lambda kv: kv[1])
    labels = {
        "fundamentals": "weak fundamentals",
        "stability": "low stability",
        "trend_quality": "trend breakdown",
        "momentum": "momentum loss",
        "risk": "elevated risk",
        "valuation": "stretched valuation",
        "growth": "weak growth",
        "confidence": "low predictive confidence",
    }
    return f"{labels.get(worst_key, worst_key)} ({worst_val:.0f}/100)"


# ----------------------------------------------------------------------
# Card rendering
# ----------------------------------------------------------------------
def _render_card(score: StockScore, mode: str, rank: int) -> str:
    final_color = _score_color(score.final_score)
    rec_color = _badge_color(score.recommendation)
    reason = _short_reason(score, mode)
    price = format_currency(score.price, score.currency or "")
    return f"""
    <div style="background:{COLORS['panel']};border:1px solid #1f2933;
                border-left:4px solid {final_color};
                border-radius:8px;padding:14px 16px;height:100%;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
            <div>
                <div style="font-size:11px;color:{COLORS['muted']};
                            letter-spacing:0.08em;">#{rank}</div>
                <div style="font-size:18px;font-weight:700;color:{COLORS['text']};
                            line-height:1.1;">{score.ticker}</div>
                <div style="font-size:12px;color:{COLORS['muted']};margin-top:2px;
                            max-width:180px;overflow:hidden;
                            text-overflow:ellipsis;white-space:nowrap;">
                    {score.company or ''}
                </div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:24px;font-weight:700;color:{final_color};
                            line-height:1;">{format_score(score.final_score)}</div>
                <div style="font-size:10px;color:{COLORS['muted']};
                            letter-spacing:0.08em;">SCORE</div>
            </div>
        </div>
        <div style="margin-top:10px;display:flex;justify-content:space-between;
                    align-items:center;">
            <div style="font-size:13px;color:{COLORS['text']};font-weight:500;">
                {price}
            </div>
            <div style="background:{rec_color}22;color:{rec_color};
                        padding:2px 8px;border-radius:4px;font-size:11px;
                        font-weight:600;letter-spacing:0.06em;">
                {score.recommendation}
            </div>
        </div>
        <div style="margin-top:8px;font-size:11px;color:{COLORS['muted']};
                    border-top:1px solid #1f2933;padding-top:6px;">
            {reason}
        </div>
    </div>
    """


def render_top_picks(
    scores: Iterable[StockScore],
    mode: str,
    *,
    n: int = 6,
    min_score: float = 60.0,
) -> None:
    """Render the headline 'top picks' card grid."""
    valid = [s for s in scores if not s.error and s.final_score >= 0]
    if not valid:
        return

    valid.sort(key=lambda s: s.final_score, reverse=True)
    top = [s for s in valid if s.final_score >= min_score][:n]
    if not top:
        # Show top regardless of threshold so the user is never empty-handed.
        top = valid[:n]

    if mode.upper() == "BUY":
        title = "BEST PICKS TO BUY NOW"
        subtitle = (f"Top {len(top)} stocks by final score, ranked under your "
                    f"current strategy and risk profile.")
    else:
        title = "BEST PICKS TO SELL NOW"
        subtitle = (f"Top {len(top)} stocks with the highest exit pressure — "
                    f"factor inversions applied for SELL mode.")

    st.markdown(
        f"""
        <div style="margin:18px 0 8px 0;">
            <div style="font-size:13px;color:{COLORS['muted']};
                        letter-spacing:0.18em;">FEATURED</div>
            <div style="font-size:22px;font-weight:700;color:{COLORS['text']};
                        margin-top:2px;">{title}</div>
            <div style="font-size:12px;color:{COLORS['muted']};
                        margin-top:2px;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols_per_row = 3
    for row_start in range(0, len(top), cols_per_row):
        row = top[row_start:row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for i, s in enumerate(row):
            cols[i].markdown(
                _render_card(s, mode, rank=row_start + i + 1),
                unsafe_allow_html=True,
            )
        # Pad incomplete rows so the grid stays aligned.
        for j in range(len(row), cols_per_row):
            cols[j].markdown("&nbsp;", unsafe_allow_html=True)

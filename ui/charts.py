"""
Plotly chart builders for the dashboard.

All charts share a common dark, instrument-panel-style theme so the UI
feels consistent and engineering-flavored.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from config.settings import COLORS
from core.signal_processing import (
    drawdown_curve,
    rolling_smooth,
    rolling_volatility,
    trend_slope,
)


# ----------------------------------------------------------------------
# Theme
# ----------------------------------------------------------------------
def _apply_theme(fig: go.Figure, height: int = 320, title: str = "") -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(color=COLORS["text"], size=14)),
        paper_bgcolor=COLORS["panel"],
        plot_bgcolor=COLORS["panel"],
        font=dict(color=COLORS["text"], size=12),
        margin=dict(l=10, r=10, t=40, b=10),
        height=height,
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h",
                    yanchor="bottom", y=1.02, x=0),
        xaxis=dict(gridcolor="#263238", zerolinecolor="#263238"),
        yaxis=dict(gridcolor="#263238", zerolinecolor="#263238"),
    )
    return fig


# ----------------------------------------------------------------------
# Charts
# ----------------------------------------------------------------------
def price_chart(history: pd.DataFrame, ticker: str) -> go.Figure:
    fig = go.Figure()
    if history is None or history.empty:
        return _apply_theme(fig, title=f"{ticker} — Price (no data)")

    close = history["Close"].astype(float)
    smoothed = rolling_smooth(close, window=21)

    fig.add_trace(go.Scatter(
        x=close.index, y=close.values,
        name="Close", mode="lines",
        line=dict(color=COLORS["primary"], width=1.6),
    ))
    fig.add_trace(go.Scatter(
        x=smoothed.index, y=smoothed.values,
        name="Trend (21d)", mode="lines",
        line=dict(color=COLORS["accent"], width=1.4, dash="dot"),
    ))
    return _apply_theme(fig, title=f"{ticker} — Price & Trend")


def trend_slope_chart(history: pd.DataFrame, ticker: str) -> go.Figure:
    fig = go.Figure()
    if history is None or history.empty:
        return _apply_theme(fig, title=f"{ticker} — Trend Slope (no data)")

    close = history["Close"].astype(float)
    slope = trend_slope(close, window=60).dropna()
    colors = [COLORS["positive"] if v >= 0 else COLORS["negative"] for v in slope.values]

    fig.add_trace(go.Bar(
        x=slope.index, y=slope.values * 100,
        marker_color=colors, name="Slope (%/day)",
    ))
    fig.add_hline(y=0, line_color=COLORS["muted"], line_width=1)
    fig.update_yaxes(title="slope (%/day)")
    return _apply_theme(fig, title=f"{ticker} — Rolling Trend Slope")


def volatility_chart(history: pd.DataFrame, ticker: str) -> go.Figure:
    fig = go.Figure()
    if history is None or history.empty:
        return _apply_theme(fig, title=f"{ticker} — Volatility (no data)")

    close = history["Close"].astype(float)
    vol = rolling_volatility(close, window=21).dropna()

    fig.add_trace(go.Scatter(
        x=vol.index, y=vol.values * 100,
        mode="lines", fill="tozeroy",
        line=dict(color=COLORS["warning"], width=1.4),
        fillcolor="rgba(255,183,77,0.15)",
        name="Annualized Vol",
    ))
    fig.update_yaxes(title="annualized vol (%)")
    return _apply_theme(fig, title=f"{ticker} — Realized Volatility")


def drawdown_chart(history: pd.DataFrame, ticker: str) -> go.Figure:
    fig = go.Figure()
    if history is None or history.empty:
        return _apply_theme(fig, title=f"{ticker} — Drawdown (no data)")

    close = history["Close"].astype(float)
    dd = drawdown_curve(close)

    fig.add_trace(go.Scatter(
        x=dd.index, y=dd.values * 100,
        mode="lines", fill="tozeroy",
        line=dict(color=COLORS["negative"], width=1.4),
        fillcolor="rgba(239,83,80,0.20)",
        name="Drawdown",
    ))
    fig.update_yaxes(title="drawdown (%)")
    return _apply_theme(fig, title=f"{ticker} — Normalized Drawdown")


def factor_contribution_chart(contrib_df: pd.DataFrame, ticker: str) -> go.Figure:
    fig = go.Figure()
    if contrib_df is None or contrib_df.empty:
        return _apply_theme(fig, title=f"{ticker} — Factor Contributions (no data)")

    colors = [
        COLORS["positive"] if v >= 0 else COLORS["negative"]
        for v in contrib_df["Contribution"].values
    ]
    fig.add_trace(go.Bar(
        x=contrib_df["Contribution"], y=contrib_df["Factor"],
        orientation="h",
        marker_color=colors,
        text=[f"{v:+.1f}" for v in contrib_df["Contribution"]],
        textposition="auto",
    ))
    fig.update_xaxes(title="Contribution to Final Score")
    fig.update_yaxes(autorange="reversed")
    return _apply_theme(fig, height=380,
                        title=f"{ticker} — Factor Contributions")


def stability_gauge(value: float, title: str = "Stability") -> go.Figure:
    value = max(0.0, min(100.0, float(value)))
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number=dict(font=dict(color=COLORS["text"], size=28)),
        title=dict(text=title, font=dict(color=COLORS["text"], size=14)),
        gauge=dict(
            axis=dict(range=[0, 100], tickcolor=COLORS["muted"]),
            bar=dict(color=COLORS["primary"]),
            bgcolor=COLORS["panel"],
            steps=[
                dict(range=[0, 33], color="rgba(239,83,80,0.30)"),
                dict(range=[33, 66], color="rgba(255,183,77,0.30)"),
                dict(range=[66, 100], color="rgba(38,166,154,0.30)"),
            ],
        ),
    ))
    return _apply_theme(fig, height=240, title="")


def risk_gauge(value: float, title: str = "Exit Risk") -> go.Figure:
    value = max(0.0, min(100.0, float(value)))
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number=dict(font=dict(color=COLORS["text"], size=28)),
        title=dict(text=title, font=dict(color=COLORS["text"], size=14)),
        gauge=dict(
            axis=dict(range=[0, 100], tickcolor=COLORS["muted"]),
            bar=dict(color=COLORS["negative"]),
            bgcolor=COLORS["panel"],
            steps=[
                dict(range=[0, 33], color="rgba(38,166,154,0.30)"),
                dict(range=[33, 66], color="rgba(255,183,77,0.30)"),
                dict(range=[66, 100], color="rgba(239,83,80,0.30)"),
            ],
        ),
    ))
    return _apply_theme(fig, height=240, title="")


def stability_radar(stability: dict[str, float], ticker: str) -> go.Figure:
    """Radar of the five engineering metrics — at-a-glance fingerprint."""
    keys = ["FSS", "DDR", "SNIR", "EST", "PCS"]
    values = [float(stability.get(k, 0.0)) for k in keys]
    values_closed = values + [values[0]]
    keys_closed = keys + [keys[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values_closed, theta=keys_closed,
        fill="toself",
        line=dict(color=COLORS["primary"], width=2),
        fillcolor="rgba(79,195,247,0.25)",
        name=ticker,
    ))
    fig.update_layout(
        polar=dict(
            bgcolor=COLORS["panel"],
            radialaxis=dict(range=[0, 100], gridcolor="#263238",
                            tickfont=dict(color=COLORS["muted"])),
            angularaxis=dict(gridcolor="#263238",
                             tickfont=dict(color=COLORS["text"])),
        ),
        showlegend=False,
    )
    return _apply_theme(fig, height=320,
                        title=f"{ticker} — Engineering Metric Profile")

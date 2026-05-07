"""
Ranking engine.

Takes a list of ``StockScore`` objects and produces a sorted dataframe
that the UI layer can drop straight into AgGrid. All filtering
(sector, market cap, score threshold) lives here so the UI stays thin.
"""
from __future__ import annotations

import math

import pandas as pd

from core.scoring_engine import StockScore
from data.ticker_loader import get_region_for_ticker


def build_ranking_dataframe(
    scores: list[StockScore],
    *,
    min_score: float = 0.0,
    sectors: list[str] | None = None,
    min_market_cap: float = 0.0,
) -> pd.DataFrame:
    """Produce the main ranked table after applying user filters."""
    rows = []
    for s in scores:
        if s.error:
            continue
        if s.final_score < min_score:
            continue
        if sectors and s.sector not in sectors:
            continue
        if min_market_cap and (
            math.isnan(s.market_cap) or s.market_cap < min_market_cap
        ):
            continue
        row = s.to_row()
        row["Region"] = s.region or get_region_for_ticker(s.ticker)
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.sort_values("Final Score", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", df.index + 1)
    return df


def available_sectors(scores: list[StockScore]) -> list[str]:
    seen: set[str] = set()
    for s in scores:
        if s.sector and s.sector != "—":
            seen.add(s.sector)
    return sorted(seen)


def summary_stats(scores: list[StockScore]) -> dict:
    """Compact stats block for the dashboard header."""
    valid = [s for s in scores if not s.error]
    if not valid:
        return {
            "total_scanned": len(scores),
            "valid": 0,
            "errors": len(scores),
            "top_score": 0.0,
            "avg_score": 0.0,
        }
    top = max(valid, key=lambda s: s.final_score)
    avg = sum(s.final_score for s in valid) / len(valid)
    return {
        "total_scanned": len(scores),
        "valid": len(valid),
        "errors": len(scores) - len(valid),
        "top_score": top.final_score,
        "top_ticker": top.ticker,
        "avg_score": avg,
    }

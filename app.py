"""
StockAnalyzer — Engineering-Grade Investment Decision System.

Run locally with:

    streamlit run app.py

The application is organized into four layers:

  data/   yfinance fetching + on-disk cache
  core/   scoring, stability metrics, ranking, exit, explainability
  ui/     Streamlit components (sidebar, dashboard, charts, tables)
  config/ central settings & constants

This file is the orchestration entry point — it wires the user's
sidebar selection into the data layer, runs scoring, and dispatches
results to the dashboard renderer.
"""
from __future__ import annotations

import streamlit as st

from config.settings import APP_ICON, APP_TITLE, COLORS, PAGE_LAYOUT
from core.ranking_engine import (
    available_sectors,
    build_ranking_dataframe,
)
from core.scoring_engine import score_many
from data.portfolio import portfolio_tickers
from data.ticker_loader import (
    get_region_for_ticker,
    get_tickers_for_regions,
)
from data.yfinance_fetcher import fetch_many
from ui.dashboard import render_empty_state, render_main_panel
from ui.sidebar import render_sidebar
from utils.logger import get_logger

log = get_logger("app")


# ----------------------------------------------------------------------
# Page setup
# ----------------------------------------------------------------------
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout=PAGE_LAYOUT,
    initial_sidebar_state="expanded",
)


# ----------------------------------------------------------------------
# Inject minimal custom CSS for the engineering-instrument feel
# ----------------------------------------------------------------------
st.markdown(
    f"""
    <style>
        .stApp {{ background: {COLORS['background']}; color: {COLORS['text']}; }}
        section[data-testid="stSidebar"] {{
            background: {COLORS['panel']};
            border-right: 1px solid #1f2933;
        }}
        h1, h2, h3, h4, h5 {{ color: {COLORS['text']}; }}
        .stButton > button[kind="primary"] {{
            background: {COLORS['primary']};
            color: #0E1117;
            border: 0;
            font-weight: 600;
            letter-spacing: 0.05em;
        }}
        div[data-testid="stMetricLabel"] {{ color: {COLORS['muted']}; }}
        div[data-testid="stMetricValue"] {{ color: {COLORS['text']}; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------
# Main banner
# ----------------------------------------------------------------------
st.markdown(
    f"""
    <div style="display:flex;align-items:center;gap:16px;
                padding:8px 0 20px 0;border-bottom:1px solid #1f2933;
                margin-bottom:20px;">
        <div style="font-size:26px;font-weight:700;color:{COLORS['primary']};
                    letter-spacing:0.04em;">STOCKANALYZER</div>
        <div style="font-size:12px;color:{COLORS['muted']};
                    text-transform:uppercase;letter-spacing:0.18em;">
            Engineering-Grade Investment Decision System
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------
# Cached pipeline steps
# ----------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def _cached_fetch(tickers: tuple[str, ...]):
    """Cache the entire fetch step keyed by ticker set."""
    return fetch_many(list(tickers))


def _resolve_ticker_universe(selection) -> list[str]:
    """Build the ticker list from the user's source selection."""
    tickers: list[str] = []
    source = (selection.source or "Universe").strip()

    if source in ("Universe", "Both"):
        tickers.extend(get_tickers_for_regions(selection.regions))
        tickers.extend(selection.custom_tickers)

    if source in ("Portfolio", "Both"):
        tickers.extend(portfolio_tickers())

    # Dedupe preserving first-seen order.
    seen: set[str] = set()
    out: list[str] = []
    for t in tickers:
        u = t.strip().upper()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ----------------------------------------------------------------------
# Session state initialization
# ----------------------------------------------------------------------
for key, default in (
    ("scores", None),
    ("bundles", None),
    ("last_selection", None),
):
    if key not in st.session_state:
        st.session_state[key] = default


# ----------------------------------------------------------------------
# Sidebar (rendered first so we can use selections downstream)
# ----------------------------------------------------------------------
sectors_for_filter: list[str] = []
if st.session_state.scores:
    sectors_for_filter = available_sectors(st.session_state.scores)

selection = render_sidebar(available_sectors=sectors_for_filter)


# ----------------------------------------------------------------------
# Run the analysis pipeline when requested
# ----------------------------------------------------------------------
if selection.run_clicked:
    universe = _resolve_ticker_universe(selection)
    if not universe:
        st.warning("No tickers selected. Choose at least one region or "
                   "enter a custom ticker.")
    else:
        progress = st.progress(0.0, text=f"Fetching {len(universe)} tickers...")

        def _on_progress(done: int, total: int) -> None:
            try:
                progress.progress(done / max(1, total),
                                  text=f"Fetched {done}/{total}")
            except Exception:
                pass

        try:
            with st.spinner("Downloading market data..."):
                bundles = fetch_many(universe, progress_callback=_on_progress)
            progress.progress(1.0, text="Scoring stocks...")

            with st.spinner("Computing engineering scores..."):
                scores = score_many(
                    bundles,
                    mode=selection.mode,
                    style=selection.style,
                    risk=selection.risk,
                    horizon=selection.horizon,
                )
                # Backfill region info for the table.
                for s in scores:
                    s.region = get_region_for_ticker(s.ticker)

            st.session_state.scores = scores
            st.session_state.bundles = bundles
            st.session_state.last_selection = selection
            progress.empty()
            st.success(
                f"Analyzed {len(scores)} tickers — "
                f"{len([s for s in scores if not s.error])} with full data."
            )
        except Exception as exc:  # last-resort guard
            log.exception("Pipeline failure")
            progress.empty()
            st.error(f"Analysis failed: {exc}")


# ----------------------------------------------------------------------
# Render results
# ----------------------------------------------------------------------
if st.session_state.scores:
    # Re-rank on every rerun so filter changes apply immediately, even
    # without a full refetch.
    df = build_ranking_dataframe(
        st.session_state.scores,
        min_score=selection.min_score,
        sectors=selection.sectors_filter or None,
        min_market_cap=selection.min_market_cap,
    )
    render_main_panel(
        df=df,
        scores=st.session_state.scores,
        bundles=st.session_state.bundles or [],
        selection=selection,
    )
else:
    render_empty_state()

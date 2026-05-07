"""
Sidebar — collects every user input that drives the analysis.

Includes a portfolio editor (st.data_editor) so users can record the
ticker, quantity, buy price, and buy date for each holding. The
`source` selector lets users analyze either the regional universe,
their portfolio, or both.
"""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from config.settings import (
    HOLDING_PERIODS,
    INVESTMENT_STYLES,
    MARKET_REGIONS,
    MODES,
    RISK_PROFILES,
)
from data.cache_manager import clear_cache
from data.portfolio import (
    PORTFOLIO_COLUMNS,
    clear_portfolio,
    dataframe_to_portfolio,
    export_portfolio_json,
    import_portfolio_json,
    load_portfolio,
    portfolio_to_dataframe,
    save_portfolio,
)


SOURCE_OPTIONS = ["Universe", "Portfolio", "Both"]


@dataclass
class UserSelection:
    mode: str
    style: str
    risk: str
    horizon: str
    source: str                # "Universe" | "Portfolio" | "Both"
    regions: list[str]
    custom_tickers: list[str]
    min_score: float
    min_market_cap: float
    sectors_filter: list[str]
    run_clicked: bool


def _parse_custom_tickers(raw: str) -> list[str]:
    if not raw:
        return []
    bits = [t.strip().upper() for t in raw.replace("\n", ",").split(",")]
    return [b for b in bits if b]


def _portfolio_editor() -> None:
    """Render the editable portfolio table and persist on save."""
    portfolio = load_portfolio()
    df = portfolio_to_dataframe(portfolio)

    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Ticker": st.column_config.TextColumn(
                "Ticker", help="yfinance symbol, e.g. AAPL or RELIANCE.NS",
                required=True,
            ),
            "Quantity": st.column_config.NumberColumn(
                "Quantity", min_value=0.0, step=1.0, format="%.4f",
            ),
            "Buy Price": st.column_config.NumberColumn(
                "Buy Price", min_value=0.0, step=0.01, format="%.2f",
            ),
            "Buy Date": st.column_config.TextColumn(
                "Buy Date", help="YYYY-MM-DD",
            ),
            "Notes": st.column_config.TextColumn("Notes"),
        },
        hide_index=True,
        key="portfolio_editor",
    )

    cols = st.columns(2)
    if cols[0].button("Save portfolio", use_container_width=True,
                      key="portfolio_save"):
        new_portfolio = dataframe_to_portfolio(edited)
        save_portfolio(new_portfolio)
        st.toast(f"Portfolio saved ({len(new_portfolio)} holdings).")
        st.rerun()
    if cols[1].button("Clear portfolio", use_container_width=True,
                      key="portfolio_clear"):
        clear_portfolio()
        st.session_state.pop("portfolio_editor", None)
        st.toast("Portfolio cleared.")
        st.rerun()

    # ------------------------------------------------------------------
    # Export — let users download their portfolio JSON so they can
    # reload it next session (data lives only in this browser session).
    # ------------------------------------------------------------------
    if portfolio:
        st.download_button(
            "Download portfolio JSON",
            data=export_portfolio_json(portfolio),
            file_name="my_portfolio.json",
            mime="application/json",
            use_container_width=True,
            key="portfolio_download",
        )

    if not portfolio:
        st.caption(
            "Empty portfolio. Add rows above (Ticker is required) and click "
            "**Save portfolio**, or use **Import from JSON** below. "
            "Data lives only in your browser session — download JSON to keep it."
        )

    # ------------------------------------------------------------------
    # JSON import — accepts canonical schema OR foreign formats with
    # aliases (symbol/shares/price/thesis, wrapped in {"portfolio":[...]}).
    # ------------------------------------------------------------------
    st.markdown("**Import from JSON**")
    uploaded = st.file_uploader(
        "Upload JSON file", type=["json"],
        key="pf_upload", label_visibility="collapsed",
    )
    pasted = st.text_area(
        "Or paste JSON",
        key="pf_paste",
        height=90,
        placeholder='{"portfolio":[{"symbol":"AAPL","shares":5,"price":150}]}',
    )

    btns = st.columns(2)
    do_merge   = btns[0].button("Merge import",   key="pf_merge_btn",
                                use_container_width=True)
    do_replace = btns[1].button("Replace import", key="pf_replace_btn",
                                use_container_width=True)
    if do_merge or do_replace:
        text = ""
        if uploaded is not None:
            try:
                text = uploaded.read().decode("utf-8")
            except Exception as exc:
                st.error(f"Could not read uploaded file: {exc}")
        if not text and pasted:
            text = pasted
        if not text:
            st.warning("Provide a JSON file or paste JSON text first.")
        else:
            try:
                n, _ = import_portfolio_json(text, merge=do_merge)
                st.success(
                    f"{'Merged' if do_merge else 'Replaced with'} "
                    f"{n} holdings."
                )
                st.session_state.pop("portfolio_editor", None)
                st.rerun()
            except Exception as exc:
                st.error(f"Import failed: {exc}")

    st.caption(
        "Recognized field aliases: `symbol/ticker`, `shares/quantity`, "
        "`price/buy_price/cost`, `date/buy_date`, `notes/thesis`. "
        "Wrappers like `{\"portfolio\": [...]}` are unwrapped automatically."
    )


def render_sidebar(available_sectors: list[str] | None = None) -> UserSelection:
    """Render the entire sidebar and return a populated ``UserSelection``."""
    available_sectors = available_sectors or []

    with st.sidebar:
        st.markdown("## Control Panel")
        st.caption("Engineering-grade investment decision system.")

        # ----- Mode -----
        mode = st.radio("Mode", MODES, horizontal=True, key="mode")

        # ----- Strategy -----
        st.markdown("### Strategy")
        style = st.selectbox(
            "Investment Style", INVESTMENT_STYLES,
            index=INVESTMENT_STYLES.index("Hybrid Engineering Mode"),
        )
        risk = st.selectbox("Risk Profile", RISK_PROFILES, index=1)
        horizon = st.selectbox("Holding Period", HOLDING_PERIODS, index=2)

        # ----- Source -----
        st.markdown("### Source")
        source = st.radio(
            "Analyze stocks from",
            SOURCE_OPTIONS,
            horizontal=True,
            help=(
                "Universe = curated regional list. "
                "Portfolio = your saved holdings. "
                "Both = combine the two."
            ),
            key="source",
        )

        # ----- Universe controls (only when relevant) -----
        regions: list[str] = []
        custom_tickers: list[str] = []
        if source in ("Universe", "Both"):
            regions = st.multiselect(
                "Market Regions", MARKET_REGIONS, default=["USA"],
                key="regions",
            )
            custom_raw = st.text_area(
                "Custom Tickers",
                placeholder="AAPL, MSFT, RELIANCE.NS, ...",
                help="Comma- or newline-separated. yfinance symbols.",
                height=80,
                key="custom_raw",
            )
            custom_tickers = _parse_custom_tickers(custom_raw)
        else:
            st.caption(
                "Source set to Portfolio — only your saved holdings will be "
                "analyzed. Manage holdings under **Portfolio** below."
            )

        # ----- Portfolio editor -----
        with st.expander("Portfolio (holdings)", expanded=(source == "Portfolio")):
            _portfolio_editor()

        # ----- Filters -----
        st.markdown("### Filters")
        min_score = st.slider("Minimum Final Score", 0, 100, 0, 5,
                              key="min_score")
        cap_choice = st.select_slider(
            "Minimum Market Cap",
            options=["Any", "100M", "1B", "10B", "100B"],
            value="Any", key="cap_choice",
        )
        cap_map = {"Any": 0, "100M": 1e8, "1B": 1e9, "10B": 1e10, "100B": 1e11}
        min_market_cap = cap_map[cap_choice]

        sectors_filter: list[str] = []
        if available_sectors:
            sectors_filter = st.multiselect(
                "Sector Filter (optional)", available_sectors, default=[],
                key="sectors_filter",
            )

        # ----- Run / cache controls -----
        st.markdown("---")
        run_clicked = st.button(
            "RUN ANALYSIS", type="primary", use_container_width=True,
        )

        with st.expander("Cache controls"):
            if st.button("Clear cache"):
                n = clear_cache()
                st.success(f"Cleared {n} cached files.")

        st.caption(
            "Powered by yfinance · Data may be delayed up to 15 minutes · "
            "For research only — not investment advice."
        )

    return UserSelection(
        mode=mode,
        style=style,
        risk=risk,
        horizon=horizon,
        source=source,
        regions=regions,
        custom_tickers=custom_tickers,
        min_score=float(min_score),
        min_market_cap=float(min_market_cap),
        sectors_filter=sectors_filter,
        run_clicked=run_clicked,
    )

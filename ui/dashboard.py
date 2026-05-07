"""
Main dashboard composition — header KPIs, top picks, ranked table,
portfolio P&L, and the per-stock drilldown.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config.settings import COLORS, DATA_DELAY_NOTE
from core.exit_engine import evaluate_exit, summarize_warnings
from core.explainability import build_contribution_table, narrative_summary
from core.ranking_engine import summary_stats
from core.scoring_engine import StockScore
from data.portfolio import (
    Holding,
    add_or_update_holding,
    compute_pnl_table,
    load_portfolio,
    remove_holding,
)
from data.yfinance_fetcher import StockData
from ui.charts import (
    drawdown_chart,
    factor_contribution_chart,
    price_chart,
    risk_gauge,
    stability_gauge,
    stability_radar,
    trend_slope_chart,
    volatility_chart,
)
from ui.sidebar import UserSelection
from ui.tables import (
    render_contribution_table,
    render_ranking_table,
    render_simple_table,
    render_warnings_table,
)
from ui.top_picks import render_top_picks
from utils.helpers import format_currency, format_score


# ----------------------------------------------------------------------
# KPI cards
# ----------------------------------------------------------------------
def _kpi_card(label: str, value: str, color: str = COLORS["primary"]) -> str:
    return f"""
    <div style="background:{COLORS['panel']};border:1px solid #1f2933;
                border-radius:8px;padding:14px 16px;height:100%;">
        <div style="font-size:11px;color:{COLORS['muted']};letter-spacing:0.06em;
                    text-transform:uppercase;">{label}</div>
        <div style="font-size:22px;font-weight:600;color:{color};margin-top:4px;">
            {value}
        </div>
    </div>
    """


def render_header(scores: list[StockScore], selection: UserSelection) -> None:
    stats = summary_stats(scores)
    cols = st.columns(5)
    cols[0].markdown(_kpi_card("Stocks Scanned", str(stats["total_scanned"])),
                     unsafe_allow_html=True)
    cols[1].markdown(_kpi_card(
        "Mode", selection.mode,
        COLORS["positive"] if selection.mode == "BUY" else COLORS["warning"]
    ), unsafe_allow_html=True)
    cols[2].markdown(_kpi_card("Strategy", selection.style),
                     unsafe_allow_html=True)
    if selection.source == "Portfolio":
        src_text = "Portfolio"
    elif selection.source == "Both":
        src_text = "Universe + Portfolio"
    else:
        src_text = ", ".join(selection.regions) if selection.regions else "—"
    cols[3].markdown(_kpi_card("Source", src_text), unsafe_allow_html=True)
    if stats["valid"]:
        top_text = f"{format_score(stats['top_score'])} · {stats.get('top_ticker','')}"
    else:
        top_text = "—"
    cols[4].markdown(_kpi_card("Top Score", top_text, COLORS["accent"]),
                     unsafe_allow_html=True)
    st.caption(DATA_DELAY_NOTE)


# ----------------------------------------------------------------------
# Portfolio P&L panel
# ----------------------------------------------------------------------
def render_portfolio_panel(scores: list[StockScore]) -> None:
    """Show P&L for every holding in the portfolio (current price × qty)."""
    portfolio = load_portfolio()
    if not portfolio:
        return

    score_by_ticker = {s.ticker: s for s in scores if not s.error}
    prices = {t: float(s.price) for t, s in score_by_ticker.items()
              if s.price == s.price}  # NaN check

    pnl_df = compute_pnl_table(portfolio, prices)
    if pnl_df.empty:
        return

    invested = pnl_df["Invested"].sum(skipna=True)
    market_value = pnl_df["Market Value"].sum(skipna=True)
    pnl_total = pnl_df["P&L"].sum(skipna=True)
    pnl_pct = ((market_value / invested - 1.0) * 100.0) if invested > 0 else float("nan")

    st.markdown("### Portfolio")
    cols = st.columns(4)
    cols[0].markdown(_kpi_card(
        "Holdings", f"{len(portfolio)}"
    ), unsafe_allow_html=True)
    cols[1].markdown(_kpi_card(
        "Invested", format_currency(invested)
    ), unsafe_allow_html=True)
    cols[2].markdown(_kpi_card(
        "Market Value", format_currency(market_value)
    ), unsafe_allow_html=True)
    pnl_color = (COLORS["positive"] if pnl_total >= 0 else COLORS["negative"])
    pnl_label = (
        f"{format_currency(pnl_total)}  "
        f"({pnl_pct:+.2f}%)" if pnl_pct == pnl_pct else format_currency(pnl_total)
    )
    cols[3].markdown(_kpi_card("P&L", pnl_label, pnl_color),
                     unsafe_allow_html=True)

    # Round + add a recommendation column from the ranking engine output.
    pnl_df["Recommendation"] = pnl_df["Ticker"].map(
        lambda t: score_by_ticker[t].recommendation
        if t in score_by_ticker else "—"
    )
    pnl_df["Final Score"] = pnl_df["Ticker"].map(
        lambda t: round(score_by_ticker[t].final_score, 1)
        if t in score_by_ticker else float("nan")
    )

    display = pnl_df.copy()
    for col in ("Buy Price", "Current Price", "Invested",
                "Market Value", "P&L"):
        display[col] = display[col].apply(
            lambda v: format_currency(v) if v == v else "—"
        )
    display["P&L %"] = pnl_df["P&L %"].apply(
        lambda v: f"{v:+.2f}%" if v == v else "—"
    )

    render_simple_table(display)


# ----------------------------------------------------------------------
# Drilldown
# ----------------------------------------------------------------------
def _portfolio_form(ticker: str) -> None:
    """Compact add/update form so the user can record a buy from the drilldown."""
    portfolio = {h.ticker: h for h in load_portfolio()}
    existing = portfolio.get(ticker, Holding(ticker=ticker))
    with st.expander(
        ("Edit holding" if ticker in portfolio else "Add to portfolio"),
        expanded=False,
    ):
        c = st.columns(4)
        qty = c[0].number_input("Quantity", min_value=0.0, step=1.0,
                                value=float(existing.quantity),
                                key=f"qty_{ticker}")
        price = c[1].number_input("Buy Price", min_value=0.0, step=0.01,
                                  value=float(existing.buy_price),
                                  key=f"price_{ticker}")
        buy_date = c[2].text_input("Buy Date (YYYY-MM-DD)",
                                   value=existing.buy_date,
                                   key=f"date_{ticker}")
        notes = c[3].text_input("Notes", value=existing.notes,
                                key=f"notes_{ticker}")

        bcols = st.columns(2)
        if bcols[0].button("Save holding", key=f"save_{ticker}",
                           use_container_width=True):
            add_or_update_holding(Holding(
                ticker=ticker, quantity=qty, buy_price=price,
                buy_date=buy_date, notes=notes,
            ))
            st.toast(f"Saved {ticker} to portfolio.")
            st.rerun()
        if ticker in portfolio:
            if bcols[1].button("Remove holding", key=f"remove_{ticker}",
                               use_container_width=True):
                remove_holding(ticker)
                st.toast(f"Removed {ticker} from portfolio.")
                st.rerun()


def render_drilldown(
    selected_ticker: str,
    bundles_by_ticker: dict[str, StockData],
    scores_by_ticker: dict[str, StockScore],
    selection: UserSelection,
) -> None:
    bundle = bundles_by_ticker.get(selected_ticker)
    score = scores_by_ticker.get(selected_ticker)
    if not bundle or not score:
        st.info(f"No data available for {selected_ticker}.")
        return

    # ---- Header strip ----
    top = st.columns([3, 1, 1, 1])
    top[0].markdown(
        f"### {score.ticker} — {score.company}  "
        f"<span style='color:{COLORS['muted']};font-size:14px'>"
        f"{score.sector} · {score.region or ''}</span>",
        unsafe_allow_html=True,
    )
    top[1].metric("Price", format_currency(score.price, score.currency or ""))
    top[2].metric("Final Score", f"{score.final_score:.1f}")
    top[3].metric("Recommendation", score.recommendation)

    _portfolio_form(selected_ticker)

    # ---- Tabs ----
    tab_overview, tab_charts, tab_explain, tab_warnings, tab_raw = st.tabs(
        ["Overview", "Charts", "Explainability", "Exit Warnings", "Raw Metrics"]
    )

    contrib = build_contribution_table(
        score, mode=selection.mode, style=selection.style,
        risk=selection.risk, horizon=selection.horizon,
    )

    with tab_overview:
        st.markdown(f"**Narrative.** {narrative_summary(score, selection.mode)}")
        cols = st.columns(3)
        with cols[0]:
            st.plotly_chart(stability_gauge(
                score.factor_scores.get("stability", 0.0),
                title="Stability Score",
            ), use_container_width=True)
        with cols[1]:
            st.plotly_chart(risk_gauge(score.exit_risk, title="Exit Risk"),
                            use_container_width=True)
        with cols[2]:
            st.plotly_chart(stability_radar(score.stability, score.ticker),
                            use_container_width=True)

    with tab_charts:
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(price_chart(bundle.history, score.ticker),
                            use_container_width=True)
            st.plotly_chart(volatility_chart(bundle.history, score.ticker),
                            use_container_width=True)
        with c2:
            st.plotly_chart(trend_slope_chart(bundle.history, score.ticker),
                            use_container_width=True)
            st.plotly_chart(drawdown_chart(bundle.history, score.ticker),
                            use_container_width=True)

    with tab_explain:
        st.plotly_chart(factor_contribution_chart(contrib, score.ticker),
                        use_container_width=True)
        with st.expander("Detailed contribution table", expanded=True):
            render_contribution_table(contrib)

    with tab_warnings:
        warnings = evaluate_exit(bundle, score)
        st.markdown(f"**{summarize_warnings(warnings)}**")
        render_warnings_table(warnings)

    with tab_raw:
        eng_df = pd.DataFrame(
            {"Metric": ["FSS", "DDR", "SNIR", "EST", "PCS"],
             "Value": [round(score.stability.get(k, 0.0), 1)
                       for k in ["FSS", "DDR", "SNIR", "EST", "PCS"]]}
        )
        st.markdown("**Engineering Metrics**")
        render_simple_table(eng_df)

        raw_df = pd.DataFrame(
            {"Metric": list(score.raw_metrics.keys()),
             "Value": [round(v, 4) for v in score.raw_metrics.values()]}
        )
        st.markdown("**Quantitative Metrics**")
        render_simple_table(raw_df)


# ----------------------------------------------------------------------
# Top-level page renderer
# ----------------------------------------------------------------------
def render_main_panel(
    df: pd.DataFrame,
    scores: list[StockScore],
    bundles: list[StockData],
    selection: UserSelection,
) -> None:
    render_header(scores, selection)

    # Top picks (the user's headline call-to-action).
    render_top_picks(scores, mode=selection.mode)

    # Portfolio P&L (only if there are holdings).
    render_portfolio_panel(scores)

    st.markdown("### Ranked Universe")

    bundles_by_ticker = {b.ticker: b for b in bundles}
    scores_by_ticker = {s.ticker: s for s in scores}

    if df is not None and not df.empty:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download ranked CSV", data=csv,
            file_name="stockanalyzer_ranking.csv", mime="text/csv",
        )

    selected_ticker = render_ranking_table(df)

    # Default-select the top-ranked ticker so the drilldown is never empty.
    if not selected_ticker and df is not None and not df.empty:
        selected_ticker = str(df.iloc[0].get("Ticker", ""))

    if selected_ticker:
        st.markdown("---")
        render_drilldown(selected_ticker, bundles_by_ticker,
                         scores_by_ticker, selection)


def render_empty_state() -> None:
    st.markdown(
        f"""
        <div style="background:{COLORS['panel']};border-radius:10px;
                    padding:30px;border:1px solid #1f2933;">
            <h3 style="color:{COLORS['text']};margin-top:0">
                Engineering-Grade Investment Decision System
            </h3>
            <p style="color:{COLORS['muted']};line-height:1.6;">
                Configure your <b>Mode</b>, <b>Strategy</b>, <b>Risk Profile</b>,
                and <b>Source</b> in the sidebar. Use <b>Universe</b> to scan
                the curated regional list, or <b>Portfolio</b> to score only
                stocks you already own. Manage holdings (ticker, quantity,
                buy price, buy date) under the <b>Portfolio</b> expander, then
                press <b>RUN ANALYSIS</b>.
            </p>
            <p style="color:{COLORS['muted']};line-height:1.6;">
                After analysis you'll see the headline <b>Best Picks to Buy
                Now</b> (or <b>Sell Now</b>), the engineering-style stability
                metrics (FSS, DDR, SNIR, EST, PCS), portfolio P&amp;L, the
                full ranked table, and per-stock factor explainability.
            </p>
            <p style="color:{COLORS['muted']};font-size:12px;margin-bottom:0">
                Data: yfinance · For research and education only — not investment advice.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

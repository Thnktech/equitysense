"""
Table renderers — uses streamlit-aggrid when available, gracefully
falls back to st.dataframe so the app never crashes if the optional
dependency is missing.

Both code paths are explicitly themed for the dark instrument-panel
look so text is always readable against the panel background.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config.settings import COLORS

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, JsCode  # type: ignore
    from st_aggrid.shared import GridUpdateMode  # type: ignore
    _AGGRID_AVAILABLE = True
except Exception:  # pragma: no cover
    _AGGRID_AVAILABLE = False


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _format_market_cap(df: pd.DataFrame) -> pd.DataFrame:
    if "Market Cap" not in df.columns:
        return df
    df = df.copy()

    def _fmt(v):
        if pd.isna(v) or v is None:
            return "—"
        v = float(v)
        if v >= 1e12: return f"{v/1e12:.2f}T"
        if v >= 1e9:  return f"{v/1e9:.2f}B"
        if v >= 1e6:  return f"{v/1e6:.2f}M"
        return f"{v:,.0f}"
    df["Market Cap"] = df["Market Cap"].apply(_fmt)
    return df


def _styled_dataframe(df: pd.DataFrame, height: int | None = 440) -> None:
    """Render a dark-themed pandas Styler so text contrasts properly."""
    if df is None or df.empty:
        st.info("No rows to display.")
        return

    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    styler = (
        df.style
        .set_properties(**{
            "background-color": COLORS["panel"],
            "color": COLORS["text"],
            "border-color": "#1f2933",
        })
        .set_table_styles([
            {"selector": "th",
             "props": [("background-color", "#1c2530"),
                       ("color", COLORS["text"]),
                       ("font-weight", "600"),
                       ("border-color", "#1f2933")]},
            {"selector": "tr:hover td",
             "props": [("background-color", "#1c2530")]},
        ])
        .format(precision=2, na_rep="—")
    )

    def _color_score(val):
        try:
            v = float(val)
        except (TypeError, ValueError):
            return ""
        if v >= 75:
            return f"color: {COLORS['positive']}; font-weight: 600;"
        if v >= 50:
            return f"color: {COLORS['warning']}; font-weight: 600;"
        if v >= 0:
            return f"color: {COLORS['negative']}; font-weight: 600;"
        return ""

    for col in ("Final Score", "Stability Score", "Score"):
        if col in df.columns:
            styler = styler.map(_color_score, subset=[col])

    if "Contribution" in df.columns:
        def _contrib_color(val):
            try:
                v = float(val)
            except (TypeError, ValueError):
                return ""
            if v > 0:
                return f"color: {COLORS['positive']}; font-weight: 600;"
            if v < 0:
                return f"color: {COLORS['negative']}; font-weight: 600;"
            return ""
        styler = styler.map(_contrib_color, subset=["Contribution"])

    if "P&L" in df.columns or "P&L %" in df.columns:
        def _pnl_color(val):
            try:
                v = float(val)
            except (TypeError, ValueError):
                return ""
            if v > 0: return f"color: {COLORS['positive']}; font-weight: 600;"
            if v < 0: return f"color: {COLORS['negative']}; font-weight: 600;"
            return ""
        for col in ("P&L", "P&L %"):
            if col in df.columns:
                styler = styler.map(_pnl_color, subset=[col])

    st.dataframe(styler, use_container_width=True,
                 height=height, hide_index=True)


# ----------------------------------------------------------------------
# Public table renderers
# ----------------------------------------------------------------------
def render_ranking_table(df: pd.DataFrame) -> str | None:
    """Render the main ranked stock table.

    Returns the ticker of the row the user has selected, if any.
    """
    if df is None or df.empty:
        st.info("No stocks matched your filters. Try lowering the score "
                "threshold or selecting more regions.")
        return None

    display_df = _format_market_cap(df)

    if _AGGRID_AVAILABLE:
        gob = GridOptionsBuilder.from_dataframe(display_df)
        gob.configure_default_column(
            filter=True, sortable=True, resizable=True,
        )
        gob.configure_selection("single", use_checkbox=False)
        gob.configure_grid_options(rowHeight=32, headerHeight=36,
                                   domLayout="normal")

        score_color = JsCode("""
        function(params) {
            const v = params.value;
            if (v === null || v === undefined) return {};
            if (v >= 75) return {color: '#26A69A', fontWeight: 600};
            if (v >= 50) return {color: '#FFB74D', fontWeight: 600};
            return {color: '#EF5350', fontWeight: 600};
        }
        """)
        gob.configure_column("Final Score", cellStyle=score_color, width=120)
        gob.configure_column("Stability Score", cellStyle=score_color, width=120)
        gob.configure_column("Exit Risk", width=100)
        gob.configure_column("Recommendation", width=140)

        try:
            grid_resp = AgGrid(
                display_df,
                gridOptions=gob.build(),
                allow_unsafe_jscode=True,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                theme="alpine-dark",
                height=440,
                fit_columns_on_grid_load=False,
                reload_data=False,
            )
            sel = grid_resp.get("selected_rows", [])
            if isinstance(sel, pd.DataFrame):
                if not sel.empty:
                    return str(sel.iloc[0].get("Ticker", "")) or None
                return None
            if sel:
                if isinstance(sel[0], dict):
                    return sel[0].get("Ticker")
        except Exception:
            # AgGrid sometimes fails on fresh installs — fall through.
            pass

    # ----- Fallback / always-readable path -----
    _styled_dataframe(display_df, height=440)
    if "Ticker" in display_df.columns and not display_df.empty:
        return st.selectbox("Inspect ticker:", display_df["Ticker"].tolist(),
                            key="fallback_table_select")
    return None


def render_warnings_table(warnings: list) -> None:
    if not warnings:
        st.success("No active exit warnings.")
        return

    rows = [{"Severity": w.severity.upper(), "Signal": w.label,
             "Detail": w.message} for w in warnings]
    df = pd.DataFrame(rows)
    _styled_dataframe(df, height=min(440, 60 + 36 * len(rows)))


def render_contribution_table(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        st.info("No contribution data yet.")
        return
    display = df[["Factor", "Score", "Weight", "Contribution"]].copy()
    display["Weight"] = display["Weight"].apply(lambda v: f"{v:.1f}%")
    _styled_dataframe(display, height=min(440, 60 + 36 * len(display)))


def render_simple_table(df: pd.DataFrame, height: int | None = None) -> None:
    """Generic dark-themed dataframe renderer for ad-hoc panels."""
    if height is None and df is not None:
        height = min(440, 60 + 36 * max(1, len(df)))
    _styled_dataframe(df, height=height)

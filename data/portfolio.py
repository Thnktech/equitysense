"""
Portfolio store — per-session in-memory holdings list.

Each holding records:
    ticker     — yfinance symbol
    quantity   — number of shares owned
    buy_price  — average cost per share
    buy_date   — ISO date string (YYYY-MM-DD)
    notes      — optional free text

Storage model
-------------
The portfolio lives in **`st.session_state`**, so every browser session
gets its own isolated copy. Nothing is written to the server's
filesystem — this is critical when the app is hosted on Streamlit
Community Cloud, where the filesystem is shared across all visitors
and would otherwise leak one user's portfolio to everyone else.

Users persist their portfolio by exporting JSON (download button) and
importing it again next session.

When the module is imported outside a Streamlit script context (e.g.
during tests), it transparently falls back to a module-level dict.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd

from utils.logger import get_logger

log = get_logger("portfolio")


SESSION_KEY = "portfolio_holdings"

# Used only when no Streamlit session is available (tests / scripts).
_FALLBACK_STORE: list["Holding"] = []


@dataclass
class Holding:
    ticker: str
    quantity: float = 0.0
    buy_price: float = 0.0
    buy_date: str = ""
    notes: str = ""

    def normalized(self) -> "Holding":
        return Holding(
            ticker=str(self.ticker or "").strip().upper(),
            quantity=float(self.quantity or 0.0),
            buy_price=float(self.buy_price or 0.0),
            buy_date=str(self.buy_date or "").strip(),
            notes=str(self.notes or "").strip(),
        )


# ----------------------------------------------------------------------
# Session-state backed store
# ----------------------------------------------------------------------
def _session_state():
    """Return ``st.session_state`` if a Streamlit script is running."""
    try:
        import streamlit as st
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx() is None:
            return None
        return st.session_state
    except Exception:
        return None


def _get_store() -> list[Holding]:
    state = _session_state()
    if state is None:
        return _FALLBACK_STORE
    if SESSION_KEY not in state:
        state[SESSION_KEY] = []
    return state[SESSION_KEY]


def _set_store(holdings: list[Holding]) -> None:
    state = _session_state()
    if state is None:
        global _FALLBACK_STORE
        _FALLBACK_STORE = list(holdings)
        return
    state[SESSION_KEY] = list(holdings)


# ----------------------------------------------------------------------
# Public CRUD
# ----------------------------------------------------------------------
def load_portfolio() -> list[Holding]:
    return list(_get_store())


def save_portfolio(holdings: Iterable[Holding]) -> None:
    cleaned: list[Holding] = []
    seen: set[str] = set()
    for h in holdings:
        n = h.normalized()
        if not n.ticker or n.ticker in seen:
            continue
        seen.add(n.ticker)
        cleaned.append(n)
    cleaned.sort(key=lambda h: h.ticker)
    _set_store(cleaned)


def portfolio_tickers() -> list[str]:
    return [h.ticker for h in load_portfolio()]


def add_or_update_holding(holding: Holding) -> list[Holding]:
    portfolio = load_portfolio()
    n = holding.normalized()
    if not n.ticker:
        return portfolio
    found = False
    for i, h in enumerate(portfolio):
        if h.ticker == n.ticker:
            portfolio[i] = n
            found = True
            break
    if not found:
        portfolio.append(n)
    save_portfolio(portfolio)
    return load_portfolio()


def remove_holding(ticker: str) -> list[Holding]:
    portfolio = load_portfolio()
    target = ticker.strip().upper()
    portfolio = [h for h in portfolio if h.ticker != target]
    save_portfolio(portfolio)
    return load_portfolio()


def clear_portfolio() -> None:
    _set_store([])


# ----------------------------------------------------------------------
# DataFrame conversions for st.data_editor
# ----------------------------------------------------------------------
PORTFOLIO_COLUMNS = ["Ticker", "Quantity", "Buy Price", "Buy Date", "Notes"]


def portfolio_to_dataframe(holdings: list[Holding] | None = None) -> pd.DataFrame:
    if holdings is None:
        holdings = load_portfolio()
    if not holdings:
        return pd.DataFrame(columns=PORTFOLIO_COLUMNS)
    return pd.DataFrame([
        {
            "Ticker": h.ticker,
            "Quantity": h.quantity,
            "Buy Price": h.buy_price,
            "Buy Date": h.buy_date,
            "Notes": h.notes,
        }
        for h in holdings
    ])


def dataframe_to_portfolio(df: pd.DataFrame) -> list[Holding]:
    out: list[Holding] = []
    if df is None or df.empty:
        return out
    for _, row in df.iterrows():
        ticker = str(row.get("Ticker", "")).strip().upper()
        if not ticker:
            continue
        try:
            qty = float(row.get("Quantity") or 0.0)
        except (TypeError, ValueError):
            qty = 0.0
        try:
            price = float(row.get("Buy Price") or 0.0)
        except (TypeError, ValueError):
            price = 0.0
        out.append(Holding(
            ticker=ticker,
            quantity=qty,
            buy_price=price,
            buy_date=str(row.get("Buy Date") or "").strip(),
            notes=str(row.get("Notes") or "").strip(),
        ))
    return out


# ----------------------------------------------------------------------
# JSON import / export
# ----------------------------------------------------------------------
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "ticker":    ("ticker", "symbol", "Ticker", "Symbol", "code"),
    "quantity":  ("quantity", "shares", "qty", "units",
                  "Quantity", "Shares"),
    "buy_price": ("buy_price", "price", "cost", "costBasis",
                  "buyPrice", "averagePrice", "avgPrice",
                  "Buy Price", "Cost"),
    "buy_date":  ("buy_date", "buyDate", "date", "purchaseDate",
                  "boughtAt", "Buy Date"),
    "notes":     ("notes", "thesis", "comment", "description", "Notes"),
}

_LIST_WRAPPER_KEYS = ("portfolio", "holdings", "positions",
                      "items", "data", "rows")


def _first_value(entry: dict, keys: Iterable[str]):
    for k in keys:
        if k in entry and entry[k] not in (None, ""):
            return entry[k]
    return None


def _entry_to_holding(entry: dict) -> Holding | None:
    if not isinstance(entry, dict):
        return None

    ticker = _first_value(entry, _FIELD_ALIASES["ticker"])
    if not ticker:
        return None

    quantity  = _first_value(entry, _FIELD_ALIASES["quantity"])  or 0
    buy_price = _first_value(entry, _FIELD_ALIASES["buy_price"]) or 0
    buy_date  = _first_value(entry, _FIELD_ALIASES["buy_date"])  or ""
    notes_raw = _first_value(entry, _FIELD_ALIASES["notes"])     or ""

    note_parts: list[str] = []
    if notes_raw:
        note_parts.append(str(notes_raw))
    conviction = entry.get("conviction") or entry.get("Conviction")
    if conviction:
        note_parts.append(f"Conviction: {conviction}")

    try:
        quantity_f = float(quantity)
    except (TypeError, ValueError):
        quantity_f = 0.0
    try:
        price_f = float(buy_price)
    except (TypeError, ValueError):
        price_f = 0.0

    return Holding(
        ticker=str(ticker),
        quantity=quantity_f,
        buy_price=price_f,
        buy_date=str(buy_date),
        notes=" · ".join(note_parts),
    ).normalized()


def import_portfolio_json(text: str, *, merge: bool = True
                          ) -> tuple[int, list[Holding]]:
    """Import portfolio data from a JSON string."""
    data = json.loads(text)

    if isinstance(data, dict):
        for key in _LIST_WRAPPER_KEYS:
            v = data.get(key)
            if isinstance(v, list):
                data = v
                break

    if not isinstance(data, list):
        raise ValueError(
            "JSON must be a list of holdings, or an object containing one "
            f"under a key like {list(_LIST_WRAPPER_KEYS)}."
        )

    imported: list[Holding] = []
    for entry in data:
        h = _entry_to_holding(entry)
        if h and h.ticker:
            imported.append(h)

    if merge:
        existing = {h.ticker: h for h in load_portfolio()}
        for h in imported:
            existing[h.ticker] = h
        final = list(existing.values())
    else:
        final = imported

    save_portfolio(final)
    return len(imported), final


def export_portfolio_json(holdings: list[Holding] | None = None) -> str:
    """Serialize the portfolio to a pretty-printed JSON string."""
    if holdings is None:
        holdings = load_portfolio()
    return json.dumps(
        {"portfolio": [asdict(h) for h in holdings]},
        indent=2,
    )


# ----------------------------------------------------------------------
# P&L computation given current prices
# ----------------------------------------------------------------------
def compute_pnl_table(holdings: list[Holding],
                      prices: dict[str, float]) -> pd.DataFrame:
    """Build a P&L dataframe given a {ticker: current_price} map."""
    rows = []
    for h in holdings:
        price_now = prices.get(h.ticker)
        invested = h.quantity * h.buy_price
        market_value = (h.quantity * price_now) if price_now else float("nan")
        if price_now and h.buy_price > 0 and h.quantity > 0:
            pnl_abs = (price_now - h.buy_price) * h.quantity
            pnl_pct = (price_now / h.buy_price - 1.0) * 100.0
        else:
            pnl_abs = float("nan")
            pnl_pct = float("nan")
        rows.append({
            "Ticker": h.ticker,
            "Quantity": h.quantity,
            "Buy Price": h.buy_price,
            "Buy Date": h.buy_date,
            "Current Price": price_now if price_now else float("nan"),
            "Invested": invested,
            "Market Value": market_value,
            "P&L": pnl_abs,
            "P&L %": pnl_pct,
        })
    return pd.DataFrame(rows)

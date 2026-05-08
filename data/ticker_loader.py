"""
Region-specific ticker universes.

For each region we expose a single function ``get_<region>_tickers()``
that returns a deduplicated list. Internally each function tries:

1. The disk cache (joblib, 24h TTL).
2. A live fetch from Wikipedia (via ``pandas.read_html``).
3. A comprehensive hardcoded fallback list.

This keeps the universe broad and fresh without depending on a paid
data API, while still working offline if Wikipedia is unreachable.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from data.cache_manager import cache_get, cache_set
from utils.logger import get_logger

log = get_logger("ticker_loader")


_UNIVERSE_TTL_SECONDS = 60 * 60 * 24  # 24h
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def _load_ticker_csv(filename: str) -> list[str]:
    """Read a one-column ticker CSV from ``assets/``. Empty list on failure."""
    path = _ASSETS_DIR / filename
    try:
        with path.open(encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = [r[0].strip() for r in reader if r and r[0].strip()]
        # Drop header if present.
        if rows and rows[0].lower() in ("symbol", "ticker", "code"):
            rows = rows[1:]
        return [r for r in rows if r]
    except Exception as exc:
        log.warning("could not read %s: %s", path, exc)
        return []


# ======================================================================
# Hardcoded fallbacks — used when Wikipedia fetch fails
# ======================================================================

# ----- USA: full S&P 500 from a shipped CSV snapshot -----
# We ship ``assets/sp500.csv`` so the deployed app has the full universe
# even when Wikipedia is unreachable from the host. Refresh by replacing
# the CSV (or letting the live Wikipedia fetcher repopulate the cache).
USA_FALLBACK: list[str] = _load_ticker_csv("sp500.csv")

# ----- Europe: DAX/FTSE/CAC/AEX large-caps from a shipped CSV snapshot -----
EUROPE_FALLBACK: list[str] = _load_ticker_csv("europe.csv")

# ----- India: Nifty 50 from a shipped CSV snapshot -----
INDIA_FALLBACK: list[str] = _load_ticker_csv("nifty50.csv")

# ----- Japan: Nikkei 225 large-caps from a shipped CSV snapshot -----
# The Nikkei 225 wiki page lists constituents only as a navbar text
# block (not a parseable table), so we maintain this snapshot manually.
JAPAN_FALLBACK: list[str] = _load_ticker_csv("nikkei225.csv")

# ----- Rest of World: curated large-caps across CA/AU/HK/KR/BR/SG/MX -----
WORLD_FALLBACK: list[str] = _load_ticker_csv("world.csv")


# ======================================================================
# Wikipedia fetchers
# ======================================================================
def _safe_read_html(url: str) -> list[pd.DataFrame]:
    """Fetch ``url`` and parse its HTML tables.

    Wikipedia returns HTTP 403 to pandas' default User-Agent, so we
    fetch the page via ``requests`` (which lets us set a realistic
    User-Agent) and pass the HTML text to ``pd.read_html``. This also
    sidesteps version-to-version differences in pandas' URL handling.
    """
    try:
        import requests
        resp = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; EquitySense/1.0; "
                    "+https://equitysense.streamlit.app)"
                )
            },
            timeout=15,
        )
        resp.raise_for_status()
        return pd.read_html(resp.text)
    except Exception as exc:
        log.warning("read_html failed for %s: %s", url, exc)
        return []


def _fetch_sp500() -> list[str]:
    """Fetch full S&P 500 list (~500 tickers)."""
    tables = _safe_read_html(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    )
    for df in tables:
        if "Symbol" in df.columns:
            symbols = (
                df["Symbol"]
                .astype(str)
                .str.replace(".", "-", regex=False)  # BRK.B -> BRK-B for yfinance
                .str.strip()
                .tolist()
            )
            return [s for s in symbols if s and s.lower() != "nan"]
    return []


def _fetch_nifty50() -> list[str]:
    """Nifty 50 constituents (~50 NSE tickers)."""
    tables = _safe_read_html("https://en.wikipedia.org/wiki/NIFTY_50")
    for df in tables:
        cols = [str(c) for c in df.columns]
        symbol_col = next(
            (c for c in cols if c.lower() in ("symbol", "ticker", "code")),
            None,
        )
        if symbol_col:
            symbols = df[symbol_col].astype(str).str.strip().tolist()
            cleaned = [s for s in symbols if s and s.lower() != "nan"]
            if cleaned:
                return [f"{s}.NS" for s in cleaned]
    return []


def _fetch_nikkei225() -> list[str]:
    """Nikkei 225 constituents (~225 .T tickers)."""
    tables = _safe_read_html("https://en.wikipedia.org/wiki/Nikkei_225")
    for df in tables:
        for col in df.columns:
            col_str = str(col).lower()
            if "code" in col_str or "ticker" in col_str:
                codes = df[col].astype(str).str.strip().tolist()
                cleaned = [c for c in codes if c.isdigit() and len(c) == 4]
                if cleaned:
                    return [f"{c}.T" for c in cleaned]
    return []


_KNOWN_EU_SUFFIXES = (
    "DE", "L", "PA", "AS", "SW", "MI", "MC", "ST", "BR", "LS", "OL",
    "HE", "VI", "CO", "IR", "WA",
)


def _attach_suffix(symbol: str, default_suffix: str) -> str | None:
    """Return ``symbol`` with the right yfinance suffix.

    - If ``symbol`` is empty / NaN → ``None``.
    - If it already ends in a known European exchange suffix → keep as-is.
    - Otherwise append ``default_suffix``.
    """
    s = str(symbol).strip().replace(" ", "")
    if not s or s.lower() == "nan":
        return None
    upper = s.upper()
    if "." in upper:
        tail = upper.rsplit(".", 1)[-1]
        if tail in _KNOWN_EU_SUFFIXES:
            return upper
    return f"{upper}.{default_suffix}"


def _fetch_european_indices() -> list[str]:
    """DAX 40 + FTSE 100 + CAC 40 + AEX combined."""
    out: list[str] = []

    def _try(url: str, suffix: str, candidates: tuple[str, ...]) -> list[str]:
        tables = _safe_read_html(url)
        for df in tables:
            for col in df.columns:
                col_str = str(col).lower()
                if any(tok in col_str for tok in candidates):
                    raw = df[col].astype(str).tolist()
                    formatted = [_attach_suffix(s, suffix) for s in raw]
                    return [s for s in formatted if s]
        return []

    out.extend(_try(
        "https://en.wikipedia.org/wiki/DAX",
        "DE", ("ticker", "symbol")
    ))
    out.extend(_try(
        "https://en.wikipedia.org/wiki/FTSE_100_Index",
        "L", ("ticker", "epic", "symbol")
    ))
    out.extend(_try(
        "https://en.wikipedia.org/wiki/CAC_40",
        "PA", ("ticker", "symbol")
    ))
    out.extend(_try(
        "https://en.wikipedia.org/wiki/AEX_index",
        "AS", ("ticker", "symbol")
    ))
    # Dedupe preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            deduped.append(t)
    return deduped


# ======================================================================
# Cached universe loaders
# ======================================================================
def _load_universe(
    key: str,
    fetcher: Callable[[], list[str]],
    fallback: list[str],
    min_count: int,
) -> list[str]:
    """Cache → live fetch → fallback."""
    cached = cache_get(f"universe_{key}", ttl_seconds=_UNIVERSE_TTL_SECONDS)
    if cached and len(cached) >= min_count:
        log.info("universe[%s]: using cached %d tickers", key, len(cached))
        return cached

    try:
        fresh = fetcher()
    except Exception as exc:
        log.warning("universe[%s]: fetcher raised %s", key, exc)
        fresh = []

    if len(fresh) >= min_count:
        cache_set(f"universe_{key}", fresh)
        log.info("universe[%s]: fetched %d tickers", key, len(fresh))
        return fresh

    log.info(
        "universe[%s]: using hardcoded fallback (%d tickers)",
        key, len(fallback)
    )
    return fallback


def get_usa_tickers() -> list[str]:
    return _load_universe("usa", _fetch_sp500, USA_FALLBACK, min_count=200)


def get_europe_tickers() -> list[str]:
    return _load_universe(
        "europe", _fetch_european_indices, EUROPE_FALLBACK, min_count=60
    )


def get_india_tickers() -> list[str]:
    return _load_universe(
        "india", _fetch_nifty50, INDIA_FALLBACK, min_count=30
    )


def get_japan_tickers() -> list[str]:
    return _load_universe(
        "japan", _fetch_nikkei225, JAPAN_FALLBACK, min_count=80
    )


def get_world_tickers() -> list[str]:
    """Rest-of-world large caps (CA/AU/HK/KR/BR/SG/MX).

    No live fetcher — the curated CSV snapshot in ``assets/world.csv``
    is the source of truth. Refresh by editing that CSV.
    """
    return _load_universe(
        "world", lambda: [], WORLD_FALLBACK, min_count=10**9
    )


def get_global_tickers() -> list[str]:
    """A balanced cross-section of all regions (~150 tickers)."""
    seen: set[str] = set()
    out: list[str] = []

    def _add(tickers: Iterable[str], cap: int) -> None:
        added = 0
        for t in tickers:
            if added >= cap:
                break
            if t and t not in seen:
                seen.add(t)
                out.append(t)
                added += 1

    _add(get_usa_tickers(),     50)
    _add(get_europe_tickers(),  30)
    _add(get_india_tickers(),   20)
    _add(get_japan_tickers(),   25)
    _add(get_world_tickers(),   30)
    return out


# ======================================================================
# Public lookup helpers
# ======================================================================
REGION_LOADERS: dict[str, Callable[[], list[str]]] = {
    "USA":    get_usa_tickers,
    "Europe": get_europe_tickers,
    "India":  get_india_tickers,
    "Japan":  get_japan_tickers,
    "World":  get_world_tickers,
    "Global": get_global_tickers,
}


def get_tickers_for_regions(regions: Iterable[str]) -> list[str]:
    """Deduplicated ticker list across all requested regions."""
    bag: set[str] = set()
    for region in regions:
        loader = REGION_LOADERS.get(region)
        if loader is None:
            continue
        try:
            bag.update(loader())
        except Exception as exc:
            log.warning("loader[%s] failed: %s", region, exc)
    return sorted(bag)


_EUROPE_SUFFIXES = {
    "DE", "L", "PA", "AS", "SW", "MI", "MC", "ST", "BR", "LS", "OL",
    "HE", "VI", "CO", "IR", "WA",
}
_WORLD_SUFFIXES = {
    "TO", "V", "AX", "HK", "KS", "KQ", "SA", "SI", "MX", "NZ", "JK",
    "BK", "TW", "SS", "SZ",
}


def get_region_for_ticker(ticker: str) -> str:
    """Best-effort region classification from a ticker symbol."""
    t = ticker.strip().upper()
    if t.endswith(".NS") or t.endswith(".BO"):
        return "India"
    if t.endswith(".T"):
        return "Japan"
    if "." in t:
        suffix = t.rsplit(".", 1)[-1]
        if suffix in _EUROPE_SUFFIXES:
            return "Europe"
        if suffix in _WORLD_SUFFIXES:
            return "World"
        return "Europe"  # unknown suffix — keep prior default
    return "USA"

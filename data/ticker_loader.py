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

from typing import Callable, Iterable

import pandas as pd

from data.cache_manager import cache_get, cache_set
from utils.logger import get_logger

log = get_logger("ticker_loader")


_UNIVERSE_TTL_SECONDS = 60 * 60 * 24  # 24h


# ======================================================================
# Hardcoded fallbacks — used when Wikipedia fetch fails
# ======================================================================

# ----- USA: ~50 mega-caps from S&P 500 -----
USA_FALLBACK: list[str] = [
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA",
    "BRK-B", "JPM", "V", "JNJ", "WMT", "PG", "MA", "HD", "DIS", "BAC",
    "ADBE", "CRM", "NFLX", "PEP", "KO", "MRK", "PFE", "INTC", "AMD",
    "ORCL", "CSCO", "T", "VZ", "XOM", "CVX", "NKE", "MCD", "COST",
    "ABT", "TMO", "AVGO", "QCOM", "TXN", "LIN", "HON", "UNH", "LLY",
    "GS", "MS", "BLK", "AXP", "BA", "CAT", "DE", "UPS", "RTX", "LMT",
]

# ----- Europe: ~80 blue chips with proper yfinance suffixes -----
EUROPE_FALLBACK: list[str] = [
    # Germany .DE
    "SAP.DE", "SIE.DE", "ALV.DE", "BAS.DE", "BMW.DE", "MBG.DE",
    "DTE.DE", "VOW3.DE", "BAYN.DE", "ADS.DE", "MUV2.DE", "IFX.DE",
    "MTX.DE", "FRE.DE", "DPW.DE", "RWE.DE", "EOAN.DE", "DBK.DE",
    # UK .L
    "SHEL.L", "AZN.L", "HSBA.L", "ULVR.L", "BP.L", "GSK.L", "RIO.L",
    "BARC.L", "LLOY.L", "REL.L", "DGE.L", "BATS.L", "LSEG.L", "CPG.L",
    "ABF.L", "NWG.L", "EXPN.L", "AAL.L", "AV.L", "GLEN.L", "IMB.L",
    "CRDA.L", "PRU.L", "TSCO.L", "BT-A.L",
    # France .PA
    "MC.PA", "OR.PA", "AIR.PA", "BNP.PA", "RMS.PA", "CDI.PA", "TTE.PA",
    "SAN.PA", "SU.PA", "DG.PA", "CS.PA", "CAP.PA", "BN.PA", "KER.PA",
    "ML.PA", "EL.PA",
    # Switzerland .SW
    "NESN.SW", "NOVN.SW", "ROG.SW", "ZURN.SW", "UBSG.SW", "ABBN.SW",
    "GIVN.SW", "LOGN.SW", "CFR.SW",
    # Netherlands .AS
    "ASML.AS", "ADYEN.AS", "PRX.AS", "INGA.AS", "AD.AS", "AKZA.AS",
    # Italy .MI
    "ENEL.MI", "STLA.MI", "ENI.MI", "ISP.MI", "UCG.MI", "RACE.MI",
    "G.MI",
    # Spain .MC
    "SAN.MC", "BBVA.MC", "IBE.MC", "ITX.MC", "TEF.MC",
    # Sweden .ST
    "VOLV-B.ST", "ATCO-A.ST", "ERIC-B.ST", "INVE-B.ST",
]

# ----- India: ~50 NSE blue chips (.NS) -----
INDIA_FALLBACK: list[str] = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "BAJFINANCE.NS",
    "HCLTECH.NS", "WIPRO.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS",
    "NESTLEIND.NS", "POWERGRID.NS", "NTPC.NS", "ONGC.NS", "TATAMOTORS.NS",
    "TATASTEEL.NS", "JSWSTEEL.NS", "ADANIENT.NS", "DRREDDY.NS", "CIPLA.NS",
    "BAJAJFINSV.NS", "GRASIM.NS", "COALINDIA.NS", "M&M.NS", "EICHERMOT.NS",
    "BPCL.NS", "BRITANNIA.NS", "HINDALCO.NS", "HEROMOTOCO.NS", "ADANIPORTS.NS",
    "INDUSINDBK.NS", "TECHM.NS", "DIVISLAB.NS", "IOC.NS", "GAIL.NS",
    "HDFCLIFE.NS", "BAJAJ-AUTO.NS", "SBILIFE.NS", "APOLLOHOSP.NS",
    "TATACONSUM.NS",
]

# ----- Japan: ~120 Nikkei 225 large caps (.T) -----
# The Nikkei 225 wiki page lists constituents only as a navbar text
# block (not a parseable table), so we maintain this list manually.
JAPAN_FALLBACK: list[str] = [
    "7203.T", "6758.T", "6861.T", "9984.T", "8306.T", "9432.T", "8035.T",
    "6098.T", "4063.T", "6367.T", "7974.T", "8316.T", "9433.T", "4502.T",
    "4543.T", "6594.T", "6902.T", "7267.T", "7751.T", "8001.T", "8031.T",
    "8058.T", "8411.T", "9020.T", "9022.T", "6273.T", "6981.T", "8801.T",
    "8802.T", "4452.T", "4568.T", "4661.T", "4901.T", "5108.T", "5401.T",
    "6326.T", "6501.T", "6503.T", "6701.T", "6752.T", "6954.T", "6971.T",
    "7011.T", "7261.T", "7269.T", "7270.T", "7733.T", "7832.T", "8002.T",
    "8053.T", "8113.T", "8267.T", "8591.T", "8604.T", "8725.T", "8766.T",
    "8830.T", "9101.T", "9501.T", "9503.T", "9531.T", "9613.T", "9735.T",
    "9766.T", "9983.T", "4307.T",
    # Additional Nikkei 225 names
    "2502.T", "2503.T", "2802.T", "2914.T", "3382.T", "3402.T", "3407.T",
    "4005.T", "4042.T", "4151.T", "4188.T", "4324.T", "4503.T", "4506.T",
    "4507.T", "4519.T", "4523.T", "4528.T", "4578.T", "4631.T", "4704.T",
    "4751.T", "4755.T", "4911.T", "5019.T", "5020.T", "5101.T", "5201.T",
    "5202.T", "5214.T", "5232.T", "5233.T", "5301.T", "5332.T", "5333.T",
    "5406.T", "5411.T", "5541.T", "5631.T", "5703.T", "5706.T", "5707.T",
    "5711.T", "5713.T", "5714.T", "5801.T", "5802.T", "5803.T", "6103.T",
    "6113.T", "6178.T", "6301.T", "6302.T", "6305.T", "6361.T", "6471.T",
    "6472.T", "6473.T", "6479.T", "6502.T", "6504.T", "6506.T", "6645.T",
    "6674.T", "6724.T", "6753.T", "6762.T", "6770.T", "6841.T", "6857.T",
    "6920.T", "6952.T", "6976.T", "6988.T", "7004.T", "7012.T", "7186.T",
    "7201.T", "7211.T", "7259.T", "7272.T", "7731.T", "7741.T", "7762.T",
    "7912.T", "8015.T", "8053.T", "8233.T", "8252.T", "8253.T", "8801.T",
    "8830.T", "9007.T", "9008.T", "9009.T", "9021.T", "9064.T", "9301.T",
    "9412.T", "9602.T", "9684.T", "9697.T", "9706.T", "9831.T",
]


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


def get_global_tickers() -> list[str]:
    """A balanced cross-section of all four regions (~120 tickers)."""
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
    _add(get_india_tickers(),   25)
    _add(get_japan_tickers(),   25)
    return out


# ======================================================================
# Public lookup helpers
# ======================================================================
REGION_LOADERS: dict[str, Callable[[], list[str]]] = {
    "USA":    get_usa_tickers,
    "Europe": get_europe_tickers,
    "India":  get_india_tickers,
    "Japan":  get_japan_tickers,
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


def get_region_for_ticker(ticker: str) -> str:
    """Best-effort region classification from a ticker symbol."""
    t = ticker.strip().upper()
    if t.endswith(".NS") or t.endswith(".BO"):
        return "India"
    if t.endswith(".T"):
        return "Japan"
    if "." in t:
        return "Europe"
    return "USA"

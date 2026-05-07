"""
Ticker universe definitions for the supported market regions.

The lists are intentionally curated (not exhaustive) so the app stays
fast on a laptop while still scanning a meaningful cross-section of
each market. Users can always type a custom ticker into the sidebar.
"""
from __future__ import annotations

from typing import Iterable

# ----------------------------------------------------------------------
# Region universes
# ----------------------------------------------------------------------
USA_TICKERS: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK-B",
    "JPM", "V", "JNJ", "WMT", "PG", "MA", "HD", "DIS", "BAC", "ADBE",
    "CRM", "NFLX", "PEP", "KO", "MRK", "PFE", "INTC", "AMD", "ORCL",
    "CSCO", "T", "VZ", "XOM", "CVX", "NKE", "MCD", "COST", "ABT",
    "TMO", "AVGO", "QCOM", "TXN", "LIN", "HON", "UNH", "LLY", "GS",
]

EUROPE_TICKERS: list[str] = [
    "ASML.AS", "SAP.DE", "SIE.DE", "MC.PA", "OR.PA", "AIR.PA", "BNP.PA",
    "TTE.PA", "RMS.PA", "CDI.PA", "NESN.SW", "ROG.SW", "NOVN.SW",
    "ULVR.L", "AZN.L", "HSBA.L", "BP.L", "SHEL.L", "GSK.L", "RIO.L",
    "DTE.DE", "BAS.DE", "BAYN.DE", "ALV.DE", "ADS.DE", "VOW3.DE",
    "ENEL.MI", "ISP.MI", "ENI.MI", "STLA.MI",
]

INDIA_TICKERS: list[str] = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "BAJFINANCE.NS",
    "HCLTECH.NS", "WIPRO.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS",
    "NESTLEIND.NS", "POWERGRID.NS", "NTPC.NS", "ONGC.NS", "TATAMOTORS.NS",
    "TATASTEEL.NS", "JSWSTEEL.NS", "ADANIENT.NS", "DRREDDY.NS", "CIPLA.NS",
]

JAPAN_TICKERS: list[str] = [
    "7203.T", "6758.T", "6861.T", "9984.T", "8306.T", "9432.T", "8035.T",
    "6098.T", "4063.T", "6367.T", "7974.T", "8316.T", "9433.T", "4502.T",
    "4543.T", "6594.T", "6902.T", "7267.T", "7751.T", "8001.T",
    "8031.T", "8058.T", "8411.T", "9020.T", "9022.T",
]

GLOBAL_TICKERS: list[str] = sorted(
    set(USA_TICKERS[:25] + EUROPE_TICKERS[:15] + INDIA_TICKERS[:15] + JAPAN_TICKERS[:10])
)


REGION_MAP: dict[str, list[str]] = {
    "USA": USA_TICKERS,
    "Europe": EUROPE_TICKERS,
    "India": INDIA_TICKERS,
    "Japan": JAPAN_TICKERS,
    "Global": GLOBAL_TICKERS,
}


def get_tickers_for_regions(regions: Iterable[str]) -> list[str]:
    """Return a deduplicated list of tickers for the requested regions."""
    bag: set[str] = set()
    for region in regions:
        bag.update(REGION_MAP.get(region, []))
    return sorted(bag)


def get_region_for_ticker(ticker: str) -> str:
    """Best-effort lookup of which region a ticker belongs to."""
    for region, tickers in REGION_MAP.items():
        if region == "Global":
            continue
        if ticker in tickers:
            return region
    if ticker.endswith(".NS") or ticker.endswith(".BO"):
        return "India"
    if ticker.endswith(".T"):
        return "Japan"
    if "." in ticker:
        return "Europe"
    return "USA"

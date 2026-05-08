"""
Global configuration constants for the StockAnalyzer platform.

Centralizing settings here keeps the rest of the codebase free from
magic numbers and makes the engine easy to tune for new strategies.
"""
from __future__ import annotations

from pathlib import Path

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
CACHE_DIR: Path = PROJECT_ROOT / "cache"
ASSETS_DIR: Path = PROJECT_ROOT / "assets"
LOG_FILE: Path = CACHE_DIR / "stockanalyzer.log"
WATCHLIST_FILE: Path = CACHE_DIR / "watchlist.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------
# Data fetching
# ----------------------------------------------------------------------
DEFAULT_HISTORY_PERIOD: str = "5y"
DEFAULT_HISTORY_INTERVAL: str = "1d"
FETCH_MAX_WORKERS: int = 8
FETCH_TIMEOUT_SECONDS: int = 25

# yfinance prices are typically delayed by ~15 minutes for most exchanges.
DATA_DELAY_NOTE: str = "Data is sourced from yfinance and may be delayed up to 15 minutes."

# ----------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------
SCORE_MIN: float = 0.0
SCORE_MAX: float = 100.0

# Numerical safety
EPS: float = 1e-9

# ----------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------
APP_TITLE: str = "StockAnalyzer — Engineering-Grade Investment Decision System"
APP_ICON: str = "::"
PAGE_LAYOUT: str = "wide"

# Color palette tuned for an engineering / instrument-panel feel.
COLORS = {
    "background": "#0E1117",
    "panel": "#161B22",
    "primary": "#4FC3F7",
    "accent": "#80CBC4",
    "positive": "#26A69A",
    "negative": "#EF5350",
    "warning": "#FFB74D",
    "muted": "#90A4AE",
    "text": "#ECEFF1",
}

# ----------------------------------------------------------------------
# Investment styles & risk profiles
# ----------------------------------------------------------------------
INVESTMENT_STYLES = [
    "Long-Term Compounder",
    "Value Investing",
    "Growth Investing",
    "Momentum Investing",
    "Swing Trading",
    "Defensive Investing",
    "Dividend Investing",
    "Hybrid Engineering Mode",
]

RISK_PROFILES = ["Conservative", "Moderate", "Aggressive"]

HOLDING_PERIODS = ["Days", "Weeks", "Months", "Years"]

MARKET_REGIONS = ["USA", "Europe", "India", "Japan", "World", "Global"]

MODES = ["BUY", "SELL"]

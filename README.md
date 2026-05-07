# StockAnalyzer — Engineering-Grade Investment Decision System

A modular, locally-hosted stock analysis and exit-strategy platform that
treats the price/fundamentals stream like an engineering signal.
Built with **Python + Streamlit** and inspired by control systems,
signal processing, and stability analysis.

> Data is sourced from **yfinance**. No paid APIs, no backend, no auth.
> 15-minute delayed data is acceptable. For research only — not
> investment advice.

---

## Highlights

- **Two analysis modes** — BUY (find candidates) and SELL (exit warnings).
- **Eight investment styles** — from Long-Term Compounder to Hybrid Engineering Mode.
- **Three risk profiles** that reweight the scoring stack dynamically.
- **Five proprietary engineering metrics**:
  - **FSS** — Financial Stability Score (control-system stability margin analogue)
  - **DDR** — Drawdown Damping Ratio (how fast price recovers from shocks)
  - **SNIR** — Signal-to-Noise Investment Ratio (DSP-style trend quality)
  - **EST** — Earnings Settling Time (controls "settling time" analogue)
  - **PCS** — Predictive Confidence Score (consistency × low randomness)
- **Weighted multi-factor fusion** with full explainability — every score
  is broken down into the eight contributing factors.
- **Exit warning engine** with severity-ranked alerts for trend
  breakdown, drawdown acceleration, volatility spikes, etc.
- **Plotly + AgGrid UI** with a dark instrument-panel feel.
- **Caching + multithreading** so a 50-ticker scan finishes in seconds.
- **CSV export, watchlist, sector + market-cap + score filters**.

---

## Installation

Requires Python **3.10+** (tested with 3.11 and 3.12).

```bash
pip install -r requirements.txt
```

That's it — no database, no extra services.

## Running

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## Folder Structure

```
project_root/
├── app.py                      # Streamlit entry point
├── requirements.txt
├── README.md
├── config/
│   └── settings.py             # central constants, themes, paths
├── data/
│   ├── ticker_loader.py        # curated regional ticker universes
│   ├── yfinance_fetcher.py     # parallel cached fetcher
│   └── cache_manager.py        # joblib-based on-disk cache
├── core/
│   ├── signal_processing.py    # smoothing, slope, vol, drawdown, SNR
│   ├── stability_metrics.py    # FSS / DDR / SNIR / EST / PCS
│   ├── factor_weights.py       # mode × style × risk × horizon weights
│   ├── scoring_engine.py       # per-stock factor and final scores
│   ├── ranking_engine.py       # filtering + sorting into a dataframe
│   ├── exit_engine.py          # SELL-mode warnings
│   └── explainability.py       # factor contribution breakdown
├── ui/
│   ├── sidebar.py              # user input controls
│   ├── dashboard.py            # KPIs, table + drilldown
│   ├── charts.py               # Plotly chart builders
│   └── tables.py               # AgGrid + fallback dataframe
├── utils/
│   ├── helpers.py              # numeric, formatting, watchlist persistence
│   └── logger.py               # rotating-file logger
├── assets/
└── cache/                      # auto-populated
```

---

## Architecture

```
   ┌──────────────┐    ┌──────────────────┐    ┌───────────────────┐
   │ ui/sidebar   │──►│  app.py (router)  │──►│ data/yfinance      │
   └──────────────┘    └──────────────────┘    │ (cached + parallel)│
                                ▼              └─────────┬─────────┘
              ┌─────────────────────────────────────────┘
              ▼
       ┌──────────────────┐    ┌────────────────────┐
       │ core/signal_     │──►│ core/stability_    │
       │ processing       │    │ metrics            │
       └──────────────────┘    └────────────────────┘
                                          │
                                          ▼
                ┌──────────────────────────────────────┐
                │ core/scoring_engine ── factor_weights│
                └─────────────────────┬───────────────┘
                                      ▼
                  ┌──────────────────────────────────┐
                  │ core/ranking_engine + explainability + exit│
                  └──────────────────────────────────┘
                                      ▼
                            ┌─────────────────┐
                            │ ui/dashboard    │
                            └─────────────────┘
```

The pipeline is one-directional and stateless inside `core/`, which
makes individual engines easy to unit-test or swap.

---

## How scoring works

Each stock is scored on **eight factors**, each on a 0–100 scale:

| Factor          | Drivers                                              |
| --------------- | ---------------------------------------------------- |
| `fundamentals`  | FSS, ROE, debt/equity                                |
| `stability`     | DDR, EST                                             |
| `trend_quality` | annualized slope + momentum consistency              |
| `momentum`      | blended 1m / 3m / 6m returns                         |
| `risk`          | realized volatility + max drawdown (higher = safer)  |
| `valuation`     | PE / PB / PS (higher = cheaper)                      |
| `growth`        | earnings + revenue growth                            |
| `confidence`    | PCS, SNIR                                            |

The user's `(mode, style, risk, horizon)` selection produces a
normalized weight vector. The weighted average becomes the **final
score** (0–100). In SELL mode the "good" factors are inverted so
deteriorating positions float to the top.

---

## Screenshots

> Place screenshots in `assets/`.

| File                          | Notes                              |
| ----------------------------- | ---------------------------------- |
| `assets/screenshot_dash.png`  | Main dashboard — KPIs + ranking    |
| `assets/screenshot_drill.png` | Drilldown — charts + factor radar  |
| `assets/screenshot_exit.png`  | SELL mode — exit warnings panel    |

(These are placeholders — capture your own once the app is running.)

---

## Future Improvements

- Persist scoring runs to a local SQLite file for trend-over-time view.
- Plug-in architecture for additional regions / custom CSV universes.
- Walk-forward backtesting of the scoring system.
- Sector-relative scoring (rank within sector before fusion).
- Optional fundamentals via Alpha Vantage / IEX as fallback to yfinance.
- Lightweight ML overlay (random forest on the eight factors) for
  forward-return calibration — kept fully optional so the deterministic
  scoring stays auditable.

---

## License & Disclaimer

Provided as-is for educational and research purposes. Not investment
advice. No warranty of fitness for any purpose.

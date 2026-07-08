# WEEKLY KEYS — Global JdK RS-Ratio & RS-Momentum Dashboard

A self-contained Relative Rotation Graph (RRG) dashboard driven by **real Yahoo Finance data**, with Weekly and Daily timeframes.

![dashboard](https://img.shields.io/badge/data-Yahoo%20Finance-blue) ![python](https://img.shields.io/badge/python-3.10%2B-green)

## How it works

```
update_rrg_data.py  ──►  rrg_current.json + rrg_trails.json  ──►  index.html
```

1. **`update_rrg_data.py`** downloads ~3 years of daily closes via [`yfinance`](https://pypi.org/project/yfinance/) for 21 assets (developed & emerging equity indices, DXY, commodities, crypto) and computes a transparent double-smoothed-EMA approximation of the JdK RS-Ratio / RS-Momentum vs the benchmark (default `^GSPC`):
   - `RS = asset ÷ benchmark`
   - `EMA1 = EMA(RS, N)` → `EMA2 = EMA(RS ÷ EMA1, N)` → **RS-Ratio** `= EMA2 × 100`
   - **RS-Momentum** `= RS-Ratio ÷ EMA(RS-Ratio, N) × 100`
   - Weekly `N=10` (standard JdK approximation) · Daily `N=50` (≈ 10 trading weeks)
2. **`index.html`** renders the RRG scatter (with real 10-point historical trails), quadrant cards (EN+TH), filters, search, and a detail table — switching Weekly/Daily instantly.

> ⚠️ The true JdK indicator (RRG Research) is proprietary and adds z-score normalization; this open approximation reproduces the rotation behaviour but absolute values differ. Indicative analysis only — not investment advice.

## Usage

```bash
pip install yfinance pandas

python update_rrg_data.py            # compute both timeframes
python update_rrg_data.py --tf W     # weekly only
python update_rrg_data.py --benchmark ^GSPC

# serve the dashboard (fetch() can't read JSON via file://)
python -m http.server 8123
# → http://localhost:8123/index.html
```

`run_rrg_update.bat` is a Windows Task Scheduler wrapper for a daily automatic update (e.g. 18:00).

## Files

| File | Purpose |
|---|---|
| `index.html` | the dashboard (Tailwind + Plotly via CDN) |
| `update_rrg_data.py` | data downloader + RRG calculator (full methodology in docstring) |
| `rrg_current.json` | latest RS-Ratio / RS-Momentum / quadrant per asset, per timeframe |
| `rrg_trails.json` | 10-point historical path per asset, per timeframe |
| `run_rrg_update.bat` | scheduled-task wrapper (logs to `rrg_update.log`) |

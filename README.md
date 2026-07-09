# WEEKLY KEYS — Global JdK RS-Ratio & RS-Momentum Dashboard

A self-contained Relative Rotation Graph (RRG) dashboard driven by **real Yahoo Finance data**, with **Weekly** and **Daily** timeframes the user can switch between.

[![Update RRG data](https://github.com/Jero-THATTHEP/weekly-keys-rrg/actions/workflows/update-rrg.yml/badge.svg)](https://github.com/Jero-THATTHEP/weekly-keys-rrg/actions/workflows/update-rrg.yml)

## How it works

```
update_rrg_data.py  ──►  rrg_current.json + rrg_trails.json  ──►  index.html
```

1. **`update_rrg_data.py`** downloads ~3 years of daily closes via [`yfinance`](https://pypi.org/project/yfinance/) for developed & emerging equity indices, DXY, commodities, and crypto, then computes a transparent double-smoothed-EMA approximation of the JdK RS-Ratio / RS-Momentum vs the benchmark (default `^GSPC`):
   - `RS = asset ÷ benchmark`
   - `EMA1 = EMA(RS, N)` → `EMA2 = EMA(RS ÷ EMA1, N)` → **RS-Ratio** `= EMA2 × 100`
   - **RS-Momentum** `= RS-Ratio ÷ EMA(RS-Ratio, N) × 100`
   - **Weekly** `N=10` (standard JdK approximation, recommended) · **Daily** `N=50` (≈ 10 trading weeks)
2. **`index.html`** renders the RRG scatter (with real 10-point historical trails), quadrant cards (EN+TH), filters, search, and a detail table — switching Weekly/Daily instantly from pre-computed JSON.

> ⚠️ The true JdK indicator (RRG Research) is proprietary and adds z-score normalization; this open approximation reproduces the rotation behaviour but absolute values differ. Indicative analysis only — not investment advice.

## Automatic daily update (07:30 UTC+7)

GitHub Actions workflow [`.github/workflows/update-rrg.yml`](.github/workflows/update-rrg.yml):

| | |
|---|---|
| **Schedule** | Every day at **07:30 Asia/Bangkok (UTC+7)** = `cron: "30 0 * * *"` (00:30 UTC) |
| **What it does** | `pip install` → `python update_rrg_data.py` → commit JSON if changed → deploy GitHub Pages |
| **Manual run** | Actions → **Update RRG data** → **Run workflow** |

Local Windows alternative: `run_rrg_update.bat` (Task Scheduler wrapper that also `git push`es).

## Local usage

```bash
pip install -r requirements.txt

python update_rrg_data.py            # both Weekly and Daily (default)
python update_rrg_data.py --tf W     # weekly only
python update_rrg_data.py --tf D     # daily only
python update_rrg_data.py --benchmark ^GSPC

# serve the dashboard (fetch() cannot read JSON via file://)
python -m http.server 8123
# → http://localhost:8123/index.html
```

## Expected JSON structure

**`rrg_current.json`**

```json
{
  "benchmark": "^GSPC",
  "generated_at": "2026-07-09 07:30 +07",
  "source": "Yahoo Finance (yfinance)",
  "timeframes": {
    "W": {
      "label": "Weekly",
      "period": 10,
      "as_of": "2026-07-03",
      "assets": [
        {
          "name": "Gold",
          "ticker": "GC=F",
          "cls": "Commodities",
          "proxy": false,
          "x": 101.234,
          "y": 99.876,
          "quadrant": "Weakening",
          "perf4w": 1.25
        }
      ],
      "skipped": [
        { "name": "MAI Index", "tickers_tried": ["^MAI.BK", "^MAI"], "reason": "..." }
      ]
    },
    "D": { "label": "Daily", "period": 50, "as_of": "...", "assets": [], "skipped": [] }
  }
}
```

**`rrg_trails.json`**

```json
{
  "generated_at": "2026-07-09 07:30 +07",
  "timeframes": {
    "W": {
      "label": "Weekly",
      "as_of": "2026-07-03",
      "assets": {
        "Gold": {
          "dates": ["2026-04-24", "...", "2026-07-03"],
          "points": [[100.1, 99.5], "...", [101.2, 99.9]]
        }
      }
    },
    "D": { "label": "Daily", "as_of": "...", "assets": {} }
  }
}
```

Trail `points` are oldest → newest so the chart can draw the real rotation path.

## Files

| File | Purpose |
|---|---|
| `index.html` | Dashboard (Tailwind + Plotly CDN) — Weekly/Daily switch, trails, methodology |
| `update_rrg_data.py` | Yahoo Finance download + JdK approximation (full methodology in docstring) |
| `rrg_current.json` | Latest RS-Ratio / RS-Momentum / quadrant per asset × timeframe |
| `rrg_trails.json` | 10-point historical path per asset × timeframe |
| `requirements.txt` | `yfinance`, `pandas` |
| `run_rrg_update.bat` | Optional local scheduled-task wrapper |
| `.github/workflows/update-rrg.yml` | Daily 07:30 UTC+7 refresh + Pages deploy |
| `.github/workflows/pages.yml` | Pages deploy on push to `main` |

## Assets & benchmark

- **Benchmark (default):** S&P 500 (`^GSPC`) — change with `--benchmark` or edit `BENCHMARK` in the script
- **Classes:** Developed, Emerging, FX, Commodities, Crypto
- Assets with thin Yahoo coverage use ETF/futures proxies (marked `proxy: true` / `*` in the UI)

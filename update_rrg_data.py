#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 WEEKLY KEYS - RRG data updater
============================================================================
Downloads real historical prices from Yahoo Finance (via `yfinance`) and
computes an open, documented approximation of the JdK RS-Ratio and
RS-Momentum for every asset vs the benchmark, in BOTH Weekly and Daily
timeframes. Results are exported as JSON for the dashboard (index.html).

USAGE
-----
    python update_rrg_data.py              # compute BOTH timeframes (default)
    python update_rrg_data.py --tf W       # weekly only
    python update_rrg_data.py --tf D       # daily only
    python update_rrg_data.py --benchmark ^GSPC   # change benchmark

Outputs (written next to this script):
    rrg_current.json   latest RS-Ratio / RS-Momentum / quadrant per asset
    rrg_trails.json    historical path (last TRAIL_LEN points) per asset

AUTOMATED REFRESH
-----------------
GitHub Actions (.github/workflows/update-rrg.yml) runs this script every day
at 07:30 Asia/Bangkok (UTC+7) = 00:30 UTC, commits the JSON if changed, and
redeploys GitHub Pages. Local alternative: run_rrg_update.bat via Task Scheduler.

The dashboard (index.html) fetches both files, so it must be served over
HTTP (e.g. `python -m http.server 8123`), not opened via file://.

METHODOLOGY (approximation of the JdK method)
---------------------------------------------
The exact JdK RS-Ratio/RS-Momentum formulas (Julius de Kempenaer /
RRG Research) are proprietary. This script uses a widely-used,
fully-transparent double-smoothed-EMA approximation:

  1. Relative Strength:        RS(t)      = AssetClose(t) / BenchmarkClose(t)
  2. First smoothing layer:    EMA1(t)    = EMA(RS, N)
  3. Second smoothing layer:   EMA2(t)    = EMA(RS / EMA1, N)
     RS-Ratio:                 RSR(t)     = EMA2(t) * 100
  4. RS-Momentum:              RSM(t)     = RSR(t) / EMA(RSR, N) * 100

  N (the smoothing period) is timeframe-dependent:
      Weekly:  N = 10   (the standard "10-week" JdK approximation)
      Daily:   N = 50   (~10 trading weeks, so both views look at a
                         comparable ~2.5-month window of behaviour)

  Interpretation: both series oscillate around 100. RSR > 100 means the
  asset has been persistently outperforming the benchmark on the smoothed
  window; RSM > 100 means that relative strength is itself accelerating.

LIMITATIONS (also disclosed in the dashboard's Methodology panel)
-----------------------------------------------------------------
  * This is an APPROXIMATION - the real JdK indicator additionally
    normalizes with a rolling z-score, so absolute values here differ
    from stockcharts.com/Optuma even though rotation shape is similar.
    The dispersion around 100 is tighter; the dashboard auto-scales axes.
  * All series are aligned on a shared calendar and forward-filled
    across non-trading days (crypto trades 7d/wk, indices don't; Asian
    and US sessions close on different days). Forward-fill can smear a
    holiday gap by one bar.
  * Yahoo Finance data is unadjusted for some indices and can be revised;
    it is good for indicative rotation work, not for execution.
  * Assets whose Yahoo symbol returns no data (or too little history for
    the smoothing window) are reported in `skipped` in rrg_current.json
    and simply omitted from the chart - the dashboard shows a notice.
============================================================================
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

# Windows consoles often default to cp1252, which can't print this project's
# Thai directory name or Unicode symbols - force UTF-8 for log output.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BENCHMARK = "^GSPC"          # default benchmark: S&P 500 (override with --benchmark)

# name shown in dashboard -> ([yahoo tickers, first with data wins], asset class)
# Fallbacks after the first entry are PROXIES (ETF/futures) used only when
# Yahoo has no data for the primary symbol; the ticker actually used is
# exported in the JSON so the dashboard can disclose it.
ASSETS = {
    # Developed markets
    "S&P 500":            (["^GSPC"],                    "Developed"),
    "Nasdaq Composite":   (["^IXIC"],                    "Developed"),
    "Euro Stoxx 50":      (["^STOXX50E", "FEZ"],         "Developed"),
    "Nikkei 225":         (["^N225", "EWJ"],             "Developed"),
    "KOSPI":              (["^KS11", "EWY"],             "Developed"),  # ^KOSPI not on Yahoo
    "Hang Seng":          (["^HSI", "EWH"],              "Developed"),
    # Emerging markets
    "TAIEX":              (["^TWII", "EWT"],             "Emerging"),
    "SET Index":          (["^SET.BK", "THD"],           "Emerging"),
    "MAI Index":          (["^MAI.BK"],                  "Emerging"),  # thin Yahoo coverage; skipped if absent
    "Shanghai Composite": (["000001.SS", "ASHR"],        "Emerging"),
    "BSE Sensex":         (["^BSESN", "INDA"],           "Emerging"),
    "VN-Index":           (["^VNINDEX.VN", "VNM"],       "Emerging"),
    # FX
    "DXY":                (["DX-Y.NYB", "UUP"],          "FX"),  # DX=F often missing on Yahoo
    # Commodities (front-month futures)
    "Gold":               (["GC=F"],                     "Commodities"),
    "Silver":             (["SI=F"],                     "Commodities"),
    "WTI Crude":          (["CL=F"],                     "Commodities"),
    "Brent Crude":        (["BZ=F"],                     "Commodities"),
    # Crypto
    "BTC":                (["BTC-USD"],                  "Crypto"),
    "ETH":                (["ETH-USD"],                  "Crypto"),
    "SOL":                (["SOL-USD"],                  "Crypto"),
    "XRP":                (["XRP-USD"],                  "Crypto"),
}

# Timeframe parameters. N = smoothing period for all three EMA layers.
# Weekly N=10 is the standard JdK approximation; Daily N=50 covers roughly
# the same ~10-trading-week span so the two views are comparable.
TIMEFRAMES = {
    "W": {"label": "Weekly", "period": 10, "perf_bars": 4},   # 4 weekly bars  = 4W performance
    "D": {"label": "Daily",  "period": 50, "perf_bars": 20},  # 20 daily bars ~= 4W performance
}

DOWNLOAD_PERIOD = "3y"   # enough daily history for N=50 double smoothing to settle
TRAIL_LEN = 10           # points of historical path exported per asset (8-12 recommended)
OUT_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Data download
# ---------------------------------------------------------------------------

def download_closes(tickers: list[str]) -> pd.DataFrame:
    """Download ~3y of DAILY closes for all tickers in one batch request.

    Everything is downloaded daily and aligned on one shared calendar
    (union of all trading days, forward-filled). The weekly view is then
    derived by resampling to Friday closes - this keeps crypto (7d/week)
    and international indices (different holidays) on the same axis.
    """
    print(f"Downloading {len(tickers)} symbols from Yahoo Finance ...")
    raw = yf.download(
        tickers=tickers,
        period=DOWNLOAD_PERIOD,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=True,
    )
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    closes = closes.sort_index()
    # Drop weekend rows introduced by crypto before ffill so index-only assets
    # aren't flat 2 bars out of 7; weekly resample uses Friday anyway.
    closes = closes[closes.index.dayofweek < 5]
    closes = closes.ffill()
    return closes


# ---------------------------------------------------------------------------
# JdK approximation (see module docstring for the full explanation)
# ---------------------------------------------------------------------------

def jdk_series(asset: pd.Series, benchmark: pd.Series, period: int) -> pd.DataFrame:
    """Return DataFrame with columns rs_ratio / rs_momentum for one asset.

    Steps (double-smoothed EMA approximation):
        RS   = asset / benchmark
        EMA1 = EMA(RS, period)                  # first smoothing layer
        EMA2 = EMA(RS / EMA1, period)           # second layer, on the ratio
        RSR  = EMA2 * 100                       # RS-Ratio, oscillates ~100
        RSM  = RSR / EMA(RSR, period) * 100     # RS-Momentum: is RSR rising?
    """
    rs = (asset / benchmark).dropna()
    ema1 = rs.ewm(span=period, adjust=False).mean()
    ema2 = (rs / ema1).ewm(span=period, adjust=False).mean()
    rs_ratio = ema2 * 100.0
    rs_momentum = rs_ratio / rs_ratio.ewm(span=period, adjust=False).mean() * 100.0
    return pd.DataFrame({"rs_ratio": rs_ratio, "rs_momentum": rs_momentum})


def quadrant(x: float, y: float) -> str:
    if x >= 100 and y >= 100:
        return "Leading"
    if x < 100 and y >= 100:
        return "Improving"
    if x >= 100 and y < 100:
        return "Weakening"
    return "Lagging"


# ---------------------------------------------------------------------------
# Per-timeframe computation
# ---------------------------------------------------------------------------

def compute_timeframe(closes: pd.DataFrame, tf: str, benchmark_ticker: str):
    """Compute current values + trails for one timeframe ('W' or 'D')."""
    cfg = TIMEFRAMES[tf]
    period, perf_bars = cfg["period"], cfg["perf_bars"]

    frame = closes.resample("W-FRI").last().dropna(how="all") if tf == "W" else closes
    bench = frame.get(benchmark_ticker)
    if bench is None or bench.dropna().empty:
        raise SystemExit(f"Benchmark {benchmark_ticker} returned no data - aborting.")

    current, trails, skipped = [], {}, []

    for name, (candidates, cls) in ASSETS.items():
        # first candidate ticker with enough history wins; later ones are proxies
        ticker, series = None, None
        for cand in candidates:
            s = frame.get(cand)
            if s is not None and s.dropna().shape[0] >= period * 3:
                ticker, series = cand, s
                break
        if series is None:
            # Not enough history for the double smoothing to be meaningful
            skipped.append({"name": name, "tickers_tried": candidates,
                            "reason": "no/insufficient Yahoo Finance data"})
            continue
        is_proxy = ticker != candidates[0]

        jdk = jdk_series(series, bench, period).dropna()
        # discard the EMA warm-up region: values there are still converging
        jdk = jdk.iloc[period * 2:]
        if jdk.shape[0] < TRAIL_LEN:
            skipped.append({"name": name, "tickers_tried": [ticker],
                            "reason": "history shorter than smoothing warm-up"})
            continue

        tail = jdk.tail(TRAIL_LEN)
        x, y = float(tail["rs_ratio"].iloc[-1]), float(tail["rs_momentum"].iloc[-1])

        # 4-week performance RELATIVE to the benchmark (percentage points)
        a, b = series.dropna(), bench.dropna()
        perf = None
        if a.shape[0] > perf_bars and b.shape[0] > perf_bars:
            perf = round(
                (a.iloc[-1] / a.iloc[-1 - perf_bars] - 1) * 100
                - (b.iloc[-1] / b.iloc[-1 - perf_bars] - 1) * 100, 2)

        current.append({
            "name": name, "ticker": ticker, "cls": cls, "proxy": is_proxy,
            "x": round(x, 3), "y": round(y, 3),
            "quadrant": quadrant(x, y), "perf4w": perf,
        })
        trails[name] = {
            "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
            "points": [[round(float(r), 3), round(float(m), 3)]
                       for r, m in zip(tail["rs_ratio"], tail["rs_momentum"])],
        }

    as_of = frame.index[-1].strftime("%Y-%m-%d")
    return ({"label": cfg["label"], "period": period, "as_of": as_of,
             "assets": current, "skipped": skipped},
            {"label": cfg["label"], "as_of": as_of, "assets": trails})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Update WEEKLY KEYS RRG JSON data")
    ap.add_argument("--tf", choices=["W", "D", "both"], default="both",
                    help="timeframe to compute (default: both)")
    ap.add_argument("--benchmark", default=BENCHMARK,
                    help=f"Yahoo ticker of the benchmark (default {BENCHMARK})")
    args = ap.parse_args()

    tfs = ["W", "D"] if args.tf == "both" else [args.tf]
    tickers = sorted({t for cands, _ in ASSETS.values() for t in cands} | {args.benchmark})
    closes = download_closes(tickers)

    # Prefer Asia/Bangkok (UTC+7) so generated_at matches the daily schedule label
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Bangkok"))
    except Exception:
        now = datetime.now(timezone.utc).astimezone()
    generated = now.strftime("%Y-%m-%d %H:%M %Z")
    current_out = {"benchmark": args.benchmark, "generated_at": generated,
                   "source": "Yahoo Finance (yfinance)", "timeframes": {}}
    trails_out = {"generated_at": generated, "timeframes": {}}

    # Preserve the other timeframe's block when running --tf W or --tf D only
    cur_path, trl_path = OUT_DIR / "rrg_current.json", OUT_DIR / "rrg_trails.json"
    if args.tf != "both":
        for path, out in ((cur_path, current_out), (trl_path, trails_out)):
            if path.exists():
                try:
                    out["timeframes"] = json.loads(path.read_text(encoding="utf-8")).get("timeframes", {})
                except (json.JSONDecodeError, OSError):
                    pass

    for tf in tfs:
        print(f"Computing {TIMEFRAMES[tf]['label']} (N={TIMEFRAMES[tf]['period']}) ...")
        cur, trl = compute_timeframe(closes, tf, args.benchmark)
        current_out["timeframes"][tf] = cur
        trails_out["timeframes"][tf] = trl
        print(f"  {len(cur['assets'])} assets ok, {len(cur['skipped'])} skipped "
              f"({', '.join(s['name'] for s in cur['skipped']) or 'none'})")

    cur_path.write_text(json.dumps(current_out, indent=1, ensure_ascii=False), encoding="utf-8")
    trl_path.write_text(json.dumps(trails_out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {cur_path.name} and {trl_path.name} -> {OUT_DIR}")


if __name__ == "__main__":
    main()
    sys.exit(0)

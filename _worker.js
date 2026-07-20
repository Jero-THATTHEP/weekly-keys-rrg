/**
 * ============================================================================
 * WEEKLY KEYS — Cloudflare Pages Function (advanced mode _worker.js)
 * ============================================================================
 * Serves /rrg_current.json and /rrg_trails.json with FRESH data computed on
 * the edge from Yahoo Finance, refreshed once per day at 08:00 Asia/Bangkok
 * (UTC+7) — so the dashboard stays up to date even when the local PC is off.
 *
 * - Same double-smoothed-EMA JdK approximation as update_rrg_data.py
 *   (RS = asset/bench; EMA1 = EMA(RS,N); EMA2 = EMA(RS/EMA1,N)*100 = RS-Ratio;
 *    RS-Momentum = RSR / EMA(RSR,N) * 100). Weekly N=10, Daily N=50.
 * - Output shape is identical to the Python script's JSON, so index.html
 *   needs no changes.
 * - On ANY failure (Yahoo blocked, timeout, …) it falls back to the static
 *   JSON files uploaded with the site (produced by update_rrg_data.py).
 * - All other paths are passed through to the static assets.
 * ============================================================================
 */

const BENCHMARK = "^GSPC";
const ASSETS = [
  // [display name, [yahoo tickers: first with data wins], class]
  ["S&P 500",            ["^GSPC"],                   "Developed"],
  ["Nasdaq Composite",   ["^IXIC"],                   "Developed"],
  ["Euro Stoxx 50",      ["^STOXX50E", "FEZ"],        "Developed"],
  ["Nikkei 225",         ["^N225", "EWJ"],            "Developed"],
  ["KOSPI",              ["^KS11", "EWY"],            "Developed"],
  ["Hang Seng",          ["^HSI", "EWH"],             "Developed"],
  ["TAIEX",              ["^TWII", "EWT"],            "Emerging"],
  ["SET Index",          ["^SET.BK", "THD"],          "Emerging"],
  ["MAI Index",          ["^MAI.BK"],                 "Emerging"],
  ["Shanghai Composite", ["000001.SS", "ASHR"],       "Emerging"],
  ["BSE Sensex",         ["^BSESN", "INDA"],          "Emerging"],
  ["VN-Index",           ["^VNINDEX.VN", "VNM"],      "Emerging"],
  ["DXY",                ["DX-Y.NYB", "UUP"],         "FX"],
  ["Gold",               ["GC=F"],                    "Commodities"],
  ["Silver",             ["SI=F"],                    "Commodities"],
  ["WTI Crude",          ["CL=F"],                    "Commodities"],
  ["Brent Crude",        ["BZ=F"],                    "Commodities"],
  ["BTC",                ["BTC-USD"],                 "Crypto"],
  ["ETH",                ["ETH-USD"],                 "Crypto"],
  ["SOL",                ["SOL-USD"],                 "Crypto"],
  ["XRP",                ["XRP-USD"],                 "Crypto"],
];
const TIMEFRAMES = { W:{label:"Weekly",period:10,perfBars:4}, D:{label:"Daily",period:50,perfBars:20} };
const TRAIL_LEN = 10;
const RANGE = "2y";                  // enough history for N=50 double smoothing

// Daily refresh anchored at 08:00 Asia/Bangkok (UTC+7): the cache "day"
// rolls over at 08:00 +07, so the first visitor after 8am each morning
// triggers a fresh computation and everyone else gets that day's data.
const REFRESH_HOUR_UTC7 = 8;
function dayBucket(){
  // shift clock back by the refresh hour so the date flips at 08:00 +07
  return new Date(Date.now() + (7 - REFRESH_HOUR_UTC7) * 3600e3).toISOString().slice(0, 10);
}
function secondsUntilNextRefresh(){
  const next = new Date(dayBucket() + "T00:00:00Z").getTime()
             + 24 * 3600e3 - (7 - REFRESH_HOUR_UTC7) * 3600e3;
  return Math.max(60, Math.floor((next - Date.now()) / 1000));
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/rrg_current.json" || url.pathname === "/rrg_trails.json") {
      try {
        return await serveRrg(url.pathname, request, env, ctx);
      } catch (e) {
        // graceful degradation: serve the static JSON deployed with the site
        const fb = await env.ASSETS.fetch(new Request(url.origin + url.pathname));
        return withHeader(fb, "x-rrg-source", "static-fallback:" + String(e).slice(0, 120));
      }
    }
    return env.ASSETS.fetch(request);
  },
};

function withHeader(res, k, v){
  const r = new Response(res.body, res);
  r.headers.set(k, v);
  return r;
}

async function serveRrg(pathname, request, env, ctx){
  const cache = caches.default;
  const day = dayBucket();
  const keyFor = p => new Request(`https://rrg-cache.internal${p}?d=${day}`);
  const hit = await cache.match(keyFor(pathname));
  if (hit) return withHeader(hit, "x-rrg-source", "edge-cache d=" + day);

  const { current, trails } = await computeAll();
  const ttl = secondsUntilNextRefresh();
  const mk = obj => new Response(JSON.stringify(obj), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": `public, s-maxage=${ttl}`,
      "x-rrg-source": "computed-live d=" + day,
    },
  });
  const curRes = mk(current), trlRes = mk(trails);
  ctx.waitUntil(cache.put(keyFor("/rrg_current.json"), curRes.clone()));
  ctx.waitUntil(cache.put(keyFor("/rrg_trails.json"), trlRes.clone()));
  return pathname === "/rrg_current.json" ? curRes : trlRes;
}

/* ---------------- Yahoo Finance download ---------------- */

async function fetchChart(symbol){
  const u = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}`
          + `?range=${RANGE}&interval=1d&events=div%2Csplit`;
  const r = await fetch(u, { headers: { "user-agent": "Mozilla/5.0 (RRG-dashboard)" },
                             cf: { cacheTtl: 3600, cacheEverything: true } });
  if (!r.ok) return null;
  const j = await r.json();
  const res = j?.chart?.result?.[0];
  if (!res?.timestamp) return null;
  const closes = res.indicators?.adjclose?.[0]?.adjclose || res.indicators?.quote?.[0]?.close;
  if (!closes) return null;
  const map = new Map();   // "YYYY-MM-DD" (UTC) -> close
  res.timestamp.forEach((ts, i) => {
    const c = closes[i];
    if (c != null && isFinite(c)) map.set(new Date(ts * 1000).toISOString().slice(0, 10), c);
  });
  return map.size ? map : null;
}

/* ---------------- math (mirrors update_rrg_data.py) ---------------- */

// pandas ewm(span=n, adjust=False): y0 = x0, y = a*x + (1-a)*y_prev
function ema(arr, n){
  const a = 2 / (n + 1), out = new Array(arr.length);
  let y = arr[0];
  for (let i = 0; i < arr.length; i++){ y = i === 0 ? arr[0] : a * arr[i] + (1 - a) * y; out[i] = y; }
  return out;
}
function jdk(asset, bench, n){
  const rs = asset.map((v, i) => v / bench[i]);
  const e1 = ema(rs, n);
  const e2 = ema(rs.map((v, i) => v / e1[i]), n);
  const rsr = e2.map(v => v * 100);
  const er = ema(rsr, n);
  const rsm = rsr.map((v, i) => v / er[i] * 100);
  return { rsr, rsm };
}
const quadrant = (x, y) => x >= 100 ? (y >= 100 ? "Leading" : "Weakening")
                                    : (y >= 100 ? "Improving" : "Lagging");
const r3 = v => Math.round(v * 1000) / 1000;

/* ---------------- full computation ---------------- */

async function computeAll(){
  // one fetch per candidate symbol, all in parallel (stays under subrequest limits)
  const symbols = [...new Set(ASSETS.flatMap(([, cands]) => cands).concat(BENCHMARK))];
  const charts = new Map();
  await Promise.all(symbols.map(async s => { charts.set(s, await fetchChart(s)); }));

  const benchMap = charts.get(BENCHMARK);
  if (!benchMap) throw new Error("benchmark download failed");

  // calendar = benchmark weekday trading days; forward-fill every asset onto it
  const calendar = [...benchMap.keys()].sort();
  const seriesOn = map => {
    let last = null;
    return calendar.map(d => (map.has(d) ? (last = map.get(d)) : last));
  };
  const benchDaily = calendar.map(d => benchMap.get(d));

  // weekly = last observation of each ISO week (Friday-labelled behaviour)
  const weekIdx = [];
  for (let i = 0; i < calendar.length; i++){
    const dow = new Date(calendar[i] + "T00:00:00Z").getUTCDay();
    const next = calendar[i + 1];
    const nextDow = next ? new Date(next + "T00:00:00Z").getUTCDay() : 0;
    if (!next || nextDow <= dow) weekIdx.push(i);   // week boundary
  }

  const now = new Date(Date.now() + 7 * 3600 * 1000);   // UTC+7
  const generated = now.toISOString().slice(0, 16).replace("T", " ") + " +07";
  const current = { benchmark: BENCHMARK, generated_at: generated,
    source: "Yahoo Finance (live, computed on Cloudflare edge)", timeframes: {} };
  const trailsOut = { generated_at: generated, timeframes: {} };

  for (const tf of ["W", "D"]){
    const { label, period, perfBars } = TIMEFRAMES[tf];
    const pick = arr => tf === "W" ? weekIdx.map(i => arr[i]) : arr;
    const dates = pick(calendar);
    const bench = pick(benchDaily);

    const assetsOut = [], skipped = [], trailAssets = {};
    for (const [name, cands, cls] of ASSETS){
      let ticker = null, full = null;
      for (const c of cands){
        const m = charts.get(c);
        if (m && m.size >= period * 3){ ticker = c; full = seriesOn(m); break; }
      }
      if (!full){ skipped.push({ name, tickers_tried: cands, reason: "no/insufficient Yahoo Finance data" }); continue; }
      const series = pick(full);
      // trim leading nulls (asset listed later than benchmark history start)
      let s0 = series.findIndex(v => v != null);
      if (s0 < 0 || series.length - s0 < period * 3){
        skipped.push({ name, tickers_tried: cands, reason: "history shorter than smoothing window" }); continue;
      }
      const a = series.slice(s0), b = bench.slice(s0), d = dates.slice(s0);
      const { rsr, rsm } = jdk(a, b, period);
      const warm = period * 2;
      if (rsr.length - warm < TRAIL_LEN){
        skipped.push({ name, tickers_tried: cands, reason: "history shorter than smoothing warm-up" }); continue;
      }
      const n = rsr.length;
      const x = rsr[n - 1], y = rsm[n - 1];
      let perf = null;
      if (n > perfBars){
        perf = Math.round(((a[n-1]/a[n-1-perfBars] - 1) - (b[n-1]/b[n-1-perfBars] - 1)) * 10000) / 100;
      }
      assetsOut.push({ name, ticker, cls, proxy: ticker !== cands[0],
        x: r3(x), y: r3(y), quadrant: quadrant(x, y), perf4w: perf });
      const t0 = n - TRAIL_LEN;
      trailAssets[name] = {
        dates: d.slice(t0),
        points: Array.from({ length: TRAIL_LEN }, (_, i) => [r3(rsr[t0 + i]), r3(rsm[t0 + i])]),
      };
    }
    const asOf = dates[dates.length - 1];
    current.timeframes[tf] = { label, period, as_of: asOf, assets: assetsOut, skipped };
    trailsOut.timeframes[tf] = { label, as_of: asOf, assets: trailAssets };
  }
  return { current, trails: trailsOut };
}

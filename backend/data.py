"""Free price data: Stooq (fast, real timeout) first, Yahoo fallback.

All batch entry points are bounded in wall-clock time so a hung upstream
can never wedge an API request: per-symbol work runs in a thread pool and
the endpoint moves on after BATCH_TIMEOUT seconds.
"""
import time
from concurrent.futures import ThreadPoolExecutor, wait

WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "AMD", "COIN", "SPY", "QQQ"]
CACHE_TTL = 60
BATCH_TIMEOUT = 18

_cache = {}  # symbol -> (ts, price)


UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

def _yahoo_chart(symbol):
    """Yahoo chart API via plain requests: fast, real timeouts, no crumb dance."""
    import requests
    for host in ("query1", "query2"):
        try:
            r = requests.get(
                f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"interval": "1d", "range": "5d"},
                timeout=10, headers=UA)
            meta = r.json()["chart"]["result"][0]["meta"]
            px = meta.get("regularMarketPrice")
            if px:
                return float(px)
        except Exception:
            continue
    return None


def _fetch_one(symbol):
    # Chart API only: fast with real timeouts. The old yfinance fallback is
    # intentionally gone — it can hang ~40s behind proxies/firewalls.
    try:
        return _yahoo_chart(symbol)
    except Exception:
        return None


def get_price(symbol):
    """Latest price, cached 60s. Never raises; None when unavailable."""
    now = time.time()
    hit = _cache.get(symbol)
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    price = _fetch_one(symbol)
    if price:
        _cache[symbol] = (now, price)
    return price


def get_prices(symbols, timeout=BATCH_TIMEOUT):
    """Prices for many symbols, bounded by `timeout` seconds total."""
    out = {s: None for s in symbols}
    # serve cache first so hung upstreams don't matter on repeat hits
    todo = [s for s in symbols
            if not (_cache.get(s) and time.time() - _cache[s][0] < CACHE_TTL)]
    for s in symbols:
        if s not in todo:
            out[s] = _cache[s][1]
    if not todo:
        return out
    # NOTE: never use `with` here — context-manager exit would wait for hung
    # workers and defeat the timeout. Shutdown without waiting instead.
    ex = ThreadPoolExecutor(max_workers=min(4, len(todo)))
    try:
        futs = {ex.submit(_fetch_one, s): s for s in todo}
        done, _ = wait(futs.keys(), timeout=timeout)
        for f in done:
            s = futs[f]
            try:
                p = f.result()
            except Exception:
                p = None
            if p:
                _cache[s] = (time.time(), p)
                out[s] = p
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return out


def get_history(symbol, period="3mo"):
    """Daily closes as a pandas Series (for strategy math). Never raises."""
    import requests
    import pandas as pd
    for host in ("query1", "query2"):
        try:
            r = requests.get(
                f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"range": period, "interval": "1d"},
                timeout=12, headers=UA)
            res = r.json()["chart"]["result"][0]
            ts = res["timestamp"]
            closes = res["indicators"]["quote"][0]["close"]
            idx = pd.to_datetime(ts, unit="s")
            s = pd.Series(closes, index=idx).dropna()
            if len(s) > 10:
                return s
        except Exception:
            continue
    return None

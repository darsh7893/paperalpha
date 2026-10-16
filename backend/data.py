"""Free price data via yfinance with Stooq fallback."""
import time

WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "AMD", "COIN", "SPY", "QQQ"]

_cache = {}  # symbol -> (ts, price)

def get_price(symbol):
    """Latest price, cached 60s."""
    now = time.time()
    if symbol in _cache and now - _cache[symbol][0] < 60:
        return _cache[symbol][1]
    price = None
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        h = t.history(period="1d", interval="1m")
        if h is not None and len(h):
            price = float(h["Close"].iloc[-1])
    except Exception:
        pass
    if price is None:
        try:
            import requests
            r = requests.get(f"https://stooq.com/q/l/?s={symbol.lower()}.us&f=sd2t2ohlcv&h&e=csv", timeout=10)
            for line in r.text.strip().splitlines()[1:]:
                parts = line.split(",")
                if len(parts) >= 7 and parts[6] not in ("N/D", ""):
                    price = float(parts[6]); break
        except Exception:
            pass
    if price:
        _cache[symbol] = (now, price)
    return price

def get_history(symbol, period="3mo"):
    """Daily closes for strategy math."""
    try:
        import yfinance as yf
        h = yf.Ticker(symbol).history(period=period, interval="1d")
        return h["Close"].dropna()
    except Exception:
        return None

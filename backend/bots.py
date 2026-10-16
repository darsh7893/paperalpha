"""Bot strategies. Each returns a list of (symbol, action, usd, reason)."""
from .data import get_history, WATCHLIST
from .news import get_news_sentiment

def momentum_signals(params=None):
    """SMA crossover + RSI filter."""
    p = params or {}
    fast, slow, rsi_buy = p.get("fast", 5), p.get("slow", 20), p.get("rsi_buy", 55)
    out = []
    for sym in WATCHLIST:
        try:
            h = get_history(sym)
            if h is None or len(h) < slow + 15:
                continue
            sma_f = h.rolling(fast).mean().iloc[-1]
            sma_s = h.rolling(slow).mean().iloc[-1]
            sma_s_prev = h.rolling(slow).mean().iloc[-2]
            # RSI
            d = h.diff()
            g = d.clip(lower=0).rolling(14).mean().iloc[-1]
            l = -d.clip(upper=0).rolling(14).mean().iloc[-1]
            rsi = 100 - 100 / (1 + g / l) if l else 50
            if sma_f > sma_s and sma_s > sma_s_prev and rsi < 70:
                out.append((sym, "buy", 2000, f"sma{fast}>{slow} rsi={rsi:.0f}"))
            elif sma_f < sma_s:
                out.append((sym, "sell", 0, f"sma{fast}<{slow}"))
        except Exception:
            continue
    return out

def news_signals(params=None):
    """Buy on strong positive news sentiment, sell on strong negative."""
    p = params or {}
    buy_th = p.get("buy_th", 0.25)
    sell_th = p.get("sell_th", -0.25)
    out = []
    for sym in WATCHLIST:
        try:
            score, heads = get_news_sentiment(sym)
            hl = (heads[0][:80] + "…") if heads else "no headlines"
            if score >= buy_th:
                out.append((sym, "buy", 1500, f"news {score:+.2f}: {hl}"))
            elif score <= sell_th:
                out.append((sym, "sell", 0, f"news {score:+.2f}: {hl}"))
        except Exception:
            continue
    return out

def ensemble_signals(weights, params=None):
    """Combine bots weighted by learned performance."""
    votes = {}  # sym -> score
    for sym, act, usd, reason in momentum_signals((params or {}).get("momentum")):
        votes.setdefault(sym, []).append((weights.get("momentum", 1), act, usd, "mom:" + reason))
    for sym, act, usd, reason in news_signals((params or {}).get("news")):
        votes.setdefault(sym, []).append((weights.get("news", 1), act, usd, "news:" + reason))
    out = []
    for sym, vs in votes.items():
        buy_w = sum(w for w, a, _, _ in vs if a == "buy")
        sell_w = sum(w for w, a, _, _ in vs if a == "sell")
        if buy_w > sell_w and buy_w >= 1.0:
            usd = max(u for _, a, u, _ in vs if a == "buy")
            out.append((sym, "buy", usd, "; ".join(r for _, a, _, r in vs if a == "buy")))
        elif sell_w > buy_w:
            out.append((sym, "sell", 0, "; ".join(r for _, a, _, r in vs if a == "sell")))
    return out

"""FastAPI server: auth, dashboard API, serves mobile frontend."""
import os, time
from typing import Optional
from fastapi import FastAPI, BackgroundTasks, Header, Cookie, Response, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import db
from . import engine
from .data import get_price, WATCHLIST
from .news import get_news_sentiment
from .learner import weights

db.init()
app = FastAPI(title="PaperAlpha")

FRONT = os.path.join(os.path.dirname(__file__), "..", "frontend")
SESSION_COOKIE = "pa_session"

# ---------- auth ----------

class Creds(BaseModel):
    username: str
    password: str

def current_user(session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE)):
    u = db.session_user(session)
    if not u:
        raise HTTPException(401, "login required")
    return u

def _set_session(resp: Response, user_id: int):
    tok = db.create_session(user_id)
    resp.set_cookie(SESSION_COOKIE, tok, httponly=True, samesite="lax",
                    max_age=30 * 86400, path="/")

@app.post("/api/register")
def api_register(c: Creds, resp: Response):
    uid, err = db.create_user(c.username, c.password)
    if err:
        raise HTTPException(400, err)
    _set_session(resp, uid)
    return {"ok": True, "username": c.username.strip().lower()}

@app.post("/api/login")
def api_login(c: Creds, resp: Response):
    u = db.verify_user(c.username, c.password)
    if not u:
        raise HTTPException(401, "bad username or password")
    _set_session(resp, u["id"])
    return {"ok": True, "username": u["username"], "is_admin": bool(u["is_admin"])}

@app.post("/api/logout")
def api_logout(resp: Response, session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE)):
    db.delete_session(session)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}

@app.get("/api/me")
def api_me(u: dict = Depends(current_user)):
    return {"username": u["username"], "is_admin": bool(u["is_admin"]),
            "bot_enabled": bool(u["bot_enabled"])}

class Settings(BaseModel):
    bot_enabled: bool

@app.get("/api/settings")
def api_get_settings(u: dict = Depends(current_user)):
    return {"bot_enabled": bool(u["bot_enabled"])}

@app.put("/api/settings")
def api_put_settings(s: Settings, u: dict = Depends(current_user)):
    db.set_bot_enabled(u["id"], s.bot_enabled)
    return {"ok": True, "bot_enabled": s.bot_enabled}

# ---------- trading ----------

class Order(BaseModel):
    symbol: str
    usd: float = 1000.0

@app.get("/api/status")
def status(u: dict = Depends(current_user)):
    uid = u["id"]
    eq, cash = engine.equity(uid)
    start = 100000.0
    return {
        "equity": round(eq, 2), "cash": round(cash, 2),
        "pnl": round(eq - start, 2), "pnl_pct": round((eq - start) / start * 100, 2),
        "positions": [
            {**p, "price": get_price(p["symbol"]),
             "value": round(p["qty"] * (get_price(p["symbol"]) or p["avg_price"]), 2)}
            for p in db.get_positions(uid)
        ],
        "weights": weights(),
        "bot_stats": db.get_bot_stats(),
        "ts": time.time(),
    }

@app.get("/api/watchlist")
def watchlist(u: dict = Depends(current_user)):
    from concurrent.futures import ThreadPoolExecutor
    from .data import get_prices, get_histories
    from .news import get_sentiments
    # prices + news concurrently so a slow source can't stack delays.
    # Sparklines load lazily via /api/sparks AFTER rows render (non-blocking).
    # News is nice-to-have: give it a shorter bound than prices.
    with ThreadPoolExecutor(max_workers=2) as ex:
        fp = ex.submit(get_prices, WATCHLIST)
        fs = ex.submit(get_sentiments, WATCHLIST, 12)
        prices, sents = fp.result(), fs.result()
    out = []
    for s in WATCHLIST:
        score, heads = sents.get(s, (0.0, []))
        out.append({"symbol": s, "price": prices.get(s),
                    "sentiment": round(score, 2),
                    "headline": heads[0] if heads else ""})
    return out

@app.get("/api/sparks")
def sparks(u: dict = Depends(current_user)):
    """30 daily closes per symbol for sparklines. Lazy: called after rows render."""
    from .data import get_histories
    hists = get_histories(WATCHLIST, "1mo", 12)
    return {s: [round(float(x), 2) for x in h.tolist()[-30:]]
            for s, h in hists.items() if h is not None and len(h)}

@app.get("/api/prices")
def prices(u: dict = Depends(current_user)):
    """Lightweight ticker for live updates: {symbol: price}."""
    from .data import get_prices
    return {s: p for s, p in get_prices(WATCHLIST, 12).items()}

def _rsi(closes, n=14):
    import pandas as pd
    s = pd.Series(closes, dtype=float)
    d = s.diff()
    gain = d.clip(lower=0).rolling(n).mean()
    loss = -d.clip(upper=0).rolling(n).mean()
    rs = gain / (loss + 1e-9)
    return float((100 - 100 / (1 + rs)).iloc[-1])

_chart_cache = {}  # symbol -> (ts, payload)

@app.get("/api/chart")
def chart(symbol: str, u: dict = Depends(current_user)):
    """6-month daily chart + stats for one symbol."""
    from .data import get_history
    sym = (symbol or "").upper()
    if sym not in WATCHLIST:
        raise HTTPException(400, "unknown symbol")
    hit = _chart_cache.get(sym)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    h = get_history(sym, "6mo")
    if h is None or len(h) < 20:
        raise HTTPException(503, "chart data unavailable")
    closes = [float(x) for x in h.tolist()]
    dates = [d.strftime("%b %d") for d in h.index]
    last, prev = closes[-1], closes[-2]
    sma20 = sum(closes[-20:]) / 20
    rng = closes[-90:]
    sent, heads = get_news_sentiment(sym)
    payload = {
        "symbol": sym, "price": round(last, 2),
        "change_pct": round((last - prev) / prev * 100, 2),
        "high_90": round(max(rng), 2), "low_90": round(min(rng), 2),
        "vs_sma20_pct": round((last - sma20) / sma20 * 100, 1),
        "rsi": round(_rsi(closes), 0),
        "sentiment": round(sent, 2), "headline": heads[0] if heads else "",
        "dates": dates[-90:], "closes": [round(c, 2) for c in closes[-90:]],
    }
    _chart_cache[sym] = (time.time(), payload)
    return payload

@app.get("/api/trades")
def trades(limit: int = 50, u: dict = Depends(current_user)):
    return db.recent_trades(u["id"], limit)

@app.post("/api/buy")
def api_buy(o: Order, u: dict = Depends(current_user)):
    return engine.buy(u["id"], o.symbol.upper(), o.usd, bot="manual", reason="manual buy")

@app.post("/api/sell")
def api_sell(o: Order, u: dict = Depends(current_user)):
    return engine.sell(u["id"], o.symbol.upper(), bot="manual", reason="manual sell")

@app.post("/api/sell_all")
def api_sell_all(u: dict = Depends(current_user)):
    return engine.sell_all(u["id"], bot="manual", reason="manual sell-all")

@app.post("/api/reset")
def api_reset(u: dict = Depends(current_user)):
    db.reset_account(u["id"])
    return {"ok": True}

# ---------- bot trigger (scheduled job, not users) ----------

@app.post("/api/run_bots")
def api_run_bots(background: BackgroundTasks, x_cron_secret: Optional[str] = Header(default=None)):
    expected = os.environ.get("CRON_SECRET", "")
    if expected and x_cron_secret != expected:
        return {"ok": False, "error": "unauthorized"}
    from bot_runner import run_cycle
    background.add_task(run_cycle)
    return {"ok": True, "started": True}

app.mount("/static", StaticFiles(directory=FRONT), name="static")

@app.get("/")
def index():
    return FileResponse(os.path.join(FRONT, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

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
    out = []
    for s in WATCHLIST:
        px = get_price(s)
        sent, heads = get_news_sentiment(s)
        out.append({"symbol": s, "price": px,
                    "sentiment": round(sent, 2),
                    "headline": heads[0] if heads else ""})
    return out

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

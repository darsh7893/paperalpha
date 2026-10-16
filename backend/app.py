"""FastAPI server: dashboard API + serves mobile frontend."""
import os, time
from fastapi import FastAPI
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

class Order(BaseModel):
    symbol: str
    usd: float = 1000.0

@app.get("/api/status")
def status():
    eq, cash = engine.equity()
    start = 100000.0
    return {
        "equity": round(eq, 2), "cash": round(cash, 2),
        "pnl": round(eq - start, 2), "pnl_pct": round((eq - start) / start * 100, 2),
        "positions": [
            {**p, "price": get_price(p["symbol"]),
             "value": round(p["qty"] * (get_price(p["symbol"]) or p["avg_price"]), 2)}
            for p in db.get_positions()
        ],
        "weights": weights(),
        "bot_stats": db.get_bot_stats(),
        "ts": time.time(),
    }

@app.get("/api/watchlist")
def watchlist():
    out = []
    for s in WATCHLIST:
        px = get_price(s)
        sent, heads = get_news_sentiment(s)
        out.append({"symbol": s, "price": px,
                    "sentiment": round(sent, 2),
                    "headline": heads[0] if heads else ""})
    return out

@app.get("/api/trades")
def trades(limit: int = 50):
    return db.recent_trades(limit)

@app.post("/api/buy")
def api_buy(o: Order):
    return engine.buy(o.symbol.upper(), o.usd, bot="manual", reason="manual buy")

@app.post("/api/sell")
def api_sell(o: Order):
    return engine.sell(o.symbol.upper(), bot="manual", reason="manual sell")

@app.post("/api/sell_all")
def api_sell_all():
    return engine.sell_all(bot="manual", reason="manual sell-all")

@app.post("/api/reset")
def api_reset():
    """Reset paper account to $100k (dev)."""
    import sqlite3
    db.set_cash(100000)
    c = db.conn(); c.execute("DELETE FROM positions"); c.execute("DELETE FROM trades")
    c.execute("UPDATE bot_stats SET trades=0, wins=0, total_pnl=0, weight=1.0")
    c.commit(); c.close()
    return {"ok": True}

app.mount("/static", StaticFiles(directory=FRONT), name="static")

@app.get("/")
def index():
    return FileResponse(os.path.join(FRONT, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

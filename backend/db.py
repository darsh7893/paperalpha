"""SQLite storage for portfolio, trades, bot performance."""
import sqlite3, os, time, json

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "trades.db"))
DB_PATH = os.path.abspath(DB_PATH)

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS portfolio (
        id INTEGER PRIMARY KEY CHECK (id=1),
        cash REAL NOT NULL DEFAULT 100000,
        updated_at REAL
    );
    CREATE TABLE IF NOT EXISTS positions (
        symbol TEXT PRIMARY KEY,
        qty REAL NOT NULL DEFAULT 0,
        avg_price REAL NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL, symbol TEXT, side TEXT, qty REAL, price REAL,
        bot TEXT, reason TEXT, pnl REAL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS bot_stats (
        bot TEXT PRIMARY KEY,
        trades INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
        total_pnl REAL DEFAULT 0, weight REAL DEFAULT 1.0,
        params TEXT DEFAULT '{}', updated_at REAL
    );
    CREATE TABLE IF NOT EXISTS prices (
        symbol TEXT, ts REAL, price REAL,
        PRIMARY KEY (symbol, ts)
    );
    """)
    c.execute("INSERT OR IGNORE INTO portfolio (id, cash, updated_at) VALUES (1, 100000, ?)", (time.time(),))
    for bot in ("news", "momentum", "ensemble"):
        c.execute("INSERT OR IGNORE INTO bot_stats (bot, updated_at) VALUES (?, ?)", (bot, time.time()))
    c.commit(); c.close()

def get_cash():
    c = conn(); r = c.execute("SELECT cash FROM portfolio WHERE id=1").fetchone(); c.close()
    return r["cash"]

def set_cash(v):
    c = conn(); c.execute("UPDATE portfolio SET cash=?, updated_at=? WHERE id=1", (v, __import__("time").time())); c.commit(); c.close()

def get_positions():
    c = conn(); rows = c.execute("SELECT * FROM positions WHERE qty != 0").fetchall(); c.close()
    return [dict(r) for r in rows]

def get_position(sym):
    c = conn(); r = c.execute("SELECT * FROM positions WHERE symbol=?", (sym,)).fetchone(); c.close()
    return dict(r) if r else {"symbol": sym, "qty": 0, "avg_price": 0}

def upsert_position(sym, qty, avg_price):
    c = conn()
    if qty == 0:
        c.execute("DELETE FROM positions WHERE symbol=?", (sym,))
    else:
        c.execute("INSERT INTO positions(symbol,qty,avg_price) VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET qty=?,avg_price=?",
                  (sym, qty, avg_price, qty, avg_price))
    c.commit(); c.close()

def log_trade(ts, symbol, side, qty, price, bot, reason, pnl=0):
    c = conn()
    c.execute("INSERT INTO trades(ts,symbol,side,qty,price,bot,reason,pnl) VALUES(?,?,?,?,?,?,?,?)",
              (ts, symbol, side, qty, price, bot, reason, pnl))
    c.commit(); c.close()

def recent_trades(limit=100):
    c = conn(); rows = c.execute("SELECT * FROM trades ORDER BY ts DESC LIMIT ?", (limit,)).fetchall(); c.close()
    return [dict(r) for r in rows]

def get_bot_stats():
    c = conn(); rows = c.execute("SELECT * FROM bot_stats").fetchall(); c.close()
    return {r["bot"]: dict(r) for r in rows}

def update_bot_stats(bot, won, pnl, weight=None, params=None):
    import time, json
    c = conn()
    s = c.execute("SELECT * FROM bot_stats WHERE bot=?", (bot,)).fetchone()
    trades = (s["trades"] or 0) + 1
    wins = (s["wins"] or 0) + (1 if won else 0)
    total = (s["total_pnl"] or 0) + pnl
    q = "UPDATE bot_stats SET trades=?, wins=?, total_pnl=?, updated_at=?"
    args = [trades, wins, total, time.time()]
    if weight is not None:
        q += ", weight=?"; args.append(weight)
    if params is not None:
        q += ", params=?"; args.append(json.dumps(params))
    q += " WHERE bot=?"
    args.append(bot)
    c.execute(q, args); c.commit(); c.close()

if __name__ == "__main__":
    init(); print("db ok:", DB_PATH)

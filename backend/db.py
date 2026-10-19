"""Storage: users, sessions, per-user paper portfolios, trades, bot stats.

Persistence: by default a local SQLite file (fine for dev). Set DATABASE_URL
to use Postgres (e.g. free Neon) instead — required for hosted deploys,
because Render's free tier wipes the local filesystem (and with it every
account) on each redeploy.
"""
import sqlite3, os, time, json, hashlib, hmac, secrets, threading

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "trades.db"))
DB_PATH = os.path.abspath(DB_PATH)
SCHEMA_VERSION = 2

_PG_URL = os.environ.get("DATABASE_URL", "").strip()
_tls = threading.local()


def _is_pg():
    return bool(_PG_URL)


class _PgResult:
    """Prefetched rows; underlying cursor is already closed (no leaks)."""

    def __init__(self, rows):
        self._rows = [dict(r) for r in rows]
        self._i = 0

    def fetchone(self):
        if self._i < len(self._rows):
            r = self._rows[self._i]
            self._i += 1
            return r
        return None

    def fetchall(self):
        r = self._rows[self._i:]
        self._i = len(self._rows)
        return r


class _PgConn:
    """Mimics the sqlite3 bits of db.py over psycopg2."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, args=()):
        import psycopg2.extras
        # sqlite uses ? placeholders; psycopg2 needs %s (no literal ?/% in our SQL)
        cur = self._raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute(sql.replace("?", "%s"), tuple(args or ()))
            rows = cur.fetchall() if cur.description else []
            return _PgResult(rows)
        finally:
            cur.close()

    def executescript(self, sql):
        for stmt in (s.strip() for s in sql.split(";")):
            if stmt:
                self.execute(stmt)

    def commit(self):
        pass  # autocommit is on; explicit commits are harmless no-ops

    def close(self):
        pass  # pooled per thread; intentionally never closed


def conn():
    if _is_pg():
        c = getattr(_tls, "pg", None)
        if c is None:
            import psycopg2
            raw = psycopg2.connect(_PG_URL)
            raw.autocommit = True
            c = _PgConn(raw)
            _tls.pg = c
        return c
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _schema(pg):
    auto = "SERIAL PRIMARY KEY" if pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    real = "DOUBLE PRECISION" if pg else "REAL"
    return f"""
        DROP TABLE IF EXISTS portfolio;
        DROP TABLE IF EXISTS positions;
        DROP TABLE IF EXISTS trades;
        CREATE TABLE users (
            id {auto},
            username TEXT UNIQUE NOT NULL,
            pass_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            bot_enabled INTEGER DEFAULT 1,
            created_at {real}
        );
        CREATE TABLE sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at {real}
        );
        CREATE TABLE portfolio (
            user_id INTEGER PRIMARY KEY,
            cash {real} NOT NULL DEFAULT 100000,
            updated_at {real}
        );
        CREATE TABLE positions (
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            qty {real} NOT NULL DEFAULT 0,
            avg_price {real} NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, symbol)
        );
        CREATE TABLE trades (
            id {auto},
            user_id INTEGER NOT NULL,
            ts {real}, symbol TEXT, side TEXT, qty {real}, price {real},
            bot TEXT, reason TEXT, pnl {real} DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS bot_stats (
            bot TEXT PRIMARY KEY,
            trades INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
            total_pnl {real} DEFAULT 0, weight {real} DEFAULT 1.0,
            params TEXT DEFAULT '{{}}', updated_at {real}
        );
        CREATE TABLE IF NOT EXISTS prices (
            symbol TEXT, ts {real}, price {real},
            PRIMARY KEY (symbol, ts)
        );
        """

def init():
    c = conn()
    c.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    row = c.execute("SELECT v FROM meta WHERE k='schema_version'").fetchone()
    ver = int(row["v"]) if row else 0
    if ver < SCHEMA_VERSION:
        # Experiment stage: rebuild into the multi-user schema.
        c.executescript(_schema(_is_pg()))
        for bot in ("news", "momentum", "ensemble"):
            if _is_pg():
                c.execute("INSERT INTO bot_stats (bot, updated_at) VALUES (?, ?) ON CONFLICT (bot) DO NOTHING",
                          (bot, time.time()))
            else:
                c.execute("INSERT OR IGNORE INTO bot_stats (bot, updated_at) VALUES (?, ?)", (bot, time.time()))
        if _is_pg():
            c.execute("INSERT INTO meta (k, v) VALUES ('schema_version', ?) "
                      "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v", (str(SCHEMA_VERSION),))
        else:
            c.execute("INSERT OR REPLACE INTO meta (k, v) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    c.commit(); c.close()

# ---------- auth ----------

def _hash(password, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", password.encode(),
                               bytes.fromhex(salt_hex), 200_000).hex()

def create_user(username, password):
    username = (username or "").strip().lower()
    if len(username) < 3:
        return None, "username must be 3+ characters"
    if len(password or "") < 4:
        return None, "password must be 4+ characters"
    salt = secrets.token_hex(16)
    ph = _hash(password, salt)
    c = conn()
    n = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    try:
        if _is_pg():
            cur = c.execute(
                "INSERT INTO users(username, pass_hash, salt, is_admin, created_at) VALUES(?,?,?,?,?) RETURNING id",
                (username, ph, salt, 1 if n == 0 else 0, time.time()))
            uid = cur.fetchone()["id"]
        else:
            cur = c.execute(
                "INSERT INTO users(username, pass_hash, salt, is_admin, created_at) VALUES(?,?,?,?,?)",
                (username, ph, salt, 1 if n == 0 else 0, time.time()))
            uid = cur.lastrowid
    except sqlite3.IntegrityError:
        c.close(); return None, "username taken"
    except Exception as e:
        # psycopg2 raises UniqueViolation for duplicate usernames
        c.close()
        if "unique" in str(e).lower():
            return None, "username taken"
        raise
    c.execute("INSERT INTO portfolio(user_id, cash, updated_at) VALUES(?,?,?)",
              (uid, 100000, time.time()))
    c.commit(); c.close()
    return uid, None

def verify_user(username, password):
    c = conn()
    r = c.execute("SELECT * FROM users WHERE username=?", ((username or "").strip().lower(),)).fetchone()
    c.close()
    if not r:
        return None
    if hmac.compare_digest(_hash(password or "", r["salt"]), r["pass_hash"]):
        return dict(r)
    return None

def create_session(user_id):
    tok = secrets.token_hex(32)
    c = conn()
    c.execute("INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)",
              (tok, user_id, time.time()))
    c.commit(); c.close()
    return tok

def session_user(token):
    if not token:
        return None
    c = conn()
    r = c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?",
                  (token,)).fetchone()
    c.close()
    return dict(r) if r else None

def delete_session(token):
    c = conn(); c.execute("DELETE FROM sessions WHERE token=?", (token,)); c.commit(); c.close()

def set_bot_enabled(user_id, enabled):
    c = conn()
    c.execute("UPDATE users SET bot_enabled=? WHERE id=?", (1 if enabled else 0, user_id))
    c.commit(); c.close()

def bot_users():
    c = conn()
    rows = c.execute("SELECT * FROM users WHERE bot_enabled=1").fetchall()
    c.close()
    return [dict(r) for r in rows]

def admin_user():
    c = conn()
    r = c.execute("SELECT * FROM users WHERE is_admin=1 ORDER BY id LIMIT 1").fetchone()
    c.close()
    return dict(r) if r else None

# ---------- per-user portfolio ----------

def get_cash(uid):
    c = conn(); r = c.execute("SELECT cash FROM portfolio WHERE user_id=?", (uid,)).fetchone(); c.close()
    return r["cash"] if r else 100000

def set_cash(uid, v):
    c = conn()
    c.execute("INSERT INTO portfolio(user_id, cash, updated_at) VALUES(?,?,?) "
              "ON CONFLICT(user_id) DO UPDATE SET cash=?, updated_at=?",
              (uid, v, time.time(), v, time.time()))
    c.commit(); c.close()

def get_positions(uid):
    c = conn(); rows = c.execute("SELECT * FROM positions WHERE user_id=? AND qty != 0", (uid,)).fetchall(); c.close()
    return [dict(r) for r in rows]

def get_position(uid, sym):
    c = conn(); r = c.execute("SELECT * FROM positions WHERE user_id=? AND symbol=?", (uid, sym)).fetchone(); c.close()
    return dict(r) if r else {"symbol": sym, "qty": 0, "avg_price": 0}

def upsert_position(uid, sym, qty, avg_price):
    c = conn()
    if qty == 0:
        c.execute("DELETE FROM positions WHERE user_id=? AND symbol=?", (uid, sym))
    else:
        c.execute("INSERT INTO positions(user_id, symbol, qty, avg_price) VALUES(?,?,?,?) "
                  "ON CONFLICT(user_id, symbol) DO UPDATE SET qty=?, avg_price=?",
                  (uid, sym, qty, avg_price, qty, avg_price))
    c.commit(); c.close()

def log_trade(uid, ts, symbol, side, qty, price, bot, reason, pnl=0):
    c = conn()
    c.execute("INSERT INTO trades(user_id, ts, symbol, side, qty, price, bot, reason, pnl) "
              "VALUES(?,?,?,?,?,?,?,?,?)",
              (uid, ts, symbol, side, qty, price, bot, reason, pnl))
    c.commit(); c.close()

def recent_trades(uid, limit=100):
    c = conn()
    rows = c.execute("SELECT * FROM trades WHERE user_id=? ORDER BY ts DESC LIMIT ?", (uid, limit)).fetchall()
    c.close()
    return [dict(r) for r in rows]

def reset_account(uid):
    c = conn()
    c.execute("DELETE FROM positions WHERE user_id=?", (uid,))
    c.execute("DELETE FROM trades WHERE user_id=?", (uid,))
    c.execute("INSERT INTO portfolio(user_id, cash, updated_at) VALUES(?,?,?) "
              "ON CONFLICT(user_id) DO UPDATE SET cash=?, updated_at=?",
              (uid, 100000, time.time(), 100000, time.time()))
    c.commit(); c.close()

# ---------- bot stats (global) ----------

def get_bot_stats():
    c = conn(); rows = c.execute("SELECT * FROM bot_stats").fetchall(); c.close()
    return {r["bot"]: dict(r) for r in rows}

def update_bot_stats(bot, won, pnl, weight=None, params=None):
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

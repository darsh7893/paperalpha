"""The learning loop: reweight bots by rolling performance + mutate params.

Simple, honest online learning:
- Every sell logs realized PnL per bot (engine does this).
- Here we convert rolling win-rate/PnL into capital weights (epsilon-greedy bandit).
- Losing bots get small random param mutations (evolutionary nudge).
No magic — over weeks the ensemble drifts toward what actually worked.
"""
import json, random, time
from . import db

EPSILON = 0.15  # exploration: keep weak bots alive a little

def reweight():
    stats = db.get_bot_stats()
    scored = {}
    for bot, s in stats.items():
        if bot == "ensemble":
            continue
        trades = s["trades"] or 0
        if trades < 3:
            scored[bot] = 1.0  # not enough data — keep neutral
            continue
        win_rate = (s["wins"] or 0) / trades
        avg_pnl = (s["total_pnl"] or 0) / trades
        # score: win-rate centered + normalized avg pnl
        scored[bot] = max(0.1, 0.5 + (win_rate - 0.5) * 2 + max(-0.5, min(0.5, avg_pnl / 500)))
    total = sum(scored.values()) or 1
    for bot, sc in scored.items():
        exploit = sc / total * len(scored)
        w = (1 - EPSILON) * exploit + EPSILON * 1.0
        # mutate params of the worst bot slightly
        s = stats[bot]
        params = json.loads(s["params"] or "{}")
        if sc == min(scored.values()) and len(scored) > 1:
            params = _mutate(bot, params)
        db.update_bot_stats(bot, won=True, pnl=0, weight=round(w, 3),
                            params=params) if False else _set_weight(bot, w, params)
    return scored

def _set_weight(bot, w, params):
    import sqlite3
    c = db.conn()
    c.execute("UPDATE bot_stats SET weight=?, params=?, updated_at=? WHERE bot=?",
              (round(w, 3), json.dumps(params), time.time(), bot))
    c.commit(); c.close()

def _mutate(bot, params):
    params = dict(params)
    if bot == "momentum":
        params["fast"] = max(3, (params.get("fast", 5) or 5) + random.choice([-1, 1]))
        params["slow"] = max(10, (params.get("slow", 20) or 20) + random.choice([-2, 2]))
    elif bot == "news":
        params["buy_th"] = round(max(0.1, (params.get("buy_th", 0.25) or 0.25) + random.choice([-0.05, 0.05])), 2)
    return params

def weights():
    return {b: s["weight"] for b, s in db.get_bot_stats().items()}

def params():
    out = {}
    for b, s in db.get_bot_stats().items():
        try:
            out[b] = json.loads(s["params"] or "{}")
        except Exception:
            out[b] = {}
    return out

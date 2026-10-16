"""Background bot loop. Run on a schedule (cron / GitHub Actions).

    python bot_runner.py --once   # one cycle now
    python bot_runner.py          # loop every 15 minutes
"""
import sys, time, argparse
sys.path.insert(0, ".")
from backend import db, engine
from backend.bots import momentum_signals, news_signals, ensemble_signals
from backend.learner import reweight, weights, params

db.init()

def run_cycle():
    w = weights(); p = params()
    users = db.bot_users()
    admin = db.admin_user()
    admin_id = admin["id"] if admin else None
    for u in users:
        uid = u["id"]
        for sym, act, usd, reason in ensemble_signals(w, p):
            if act == "buy":
                engine.buy(uid, sym, usd, bot="ensemble", reason=reason[:300])
            else:
                engine.sell(uid, sym, bot="ensemble", reason=reason[:300])
        # per-bot sleeves (learning data) run only on the admin account
        if uid == admin_id:
            for bot_name, fn in (("momentum", momentum_signals), ("news", news_signals)):
                for sym, act, usd, reason in fn((p.get(bot_name) or {}))[:2]:
                    if act == "buy":
                        engine.buy(uid, sym, min(usd, 500), bot=bot_name, reason=reason[:300])
    scores = reweight()
    info = []
    for u in users:
        eq, cash = engine.equity(u["id"])
        info.append(f"{u['username']}=${eq:,.0f}")
    print(f"cycle done: {' '.join(info)} scores={scores}")
    return True

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=900)
    a = ap.parse_args()
    if a.once:
        run_cycle()
    else:
        while True:
            try:
                run_cycle()
            except Exception as e:
                print("cycle error:", e)
            time.sleep(a.interval)

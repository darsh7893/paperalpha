"""Background bot loop. Run on a schedule (cron / Render cron job).

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
    actions = []
    # individual bots vote; ensemble executes the weighted decision
    for sym, act, usd, reason in ensemble_signals(w, p):
        if act == "buy":
            r = engine.buy(sym, usd, bot="ensemble", reason=reason[:300])
        else:
            r = engine.sell(sym, bot="ensemble", reason=reason[:300])
        actions.append((sym, act, r))
    # also let each bot paper-trade a tiny sleeve so learner has per-bot data
    for bot_name, fn in (("momentum", momentum_signals), ("news", news_signals)):
        for sym, act, usd, reason in fn((p.get(bot_name) or {}))[:2]:
            if act == "buy":
                engine.buy(sym, min(usd, 500), bot=bot_name, reason=reason[:300])
            else:
                # don't dump ensemble positions from sleeves; only close bot's own tiny buys
                pass
    scores = reweight()
    eq, cash = engine.equity()
    print(f"cycle done: equity=${eq:,.0f} cash=${cash:,.0f} weights={w} scores={scores}")
    return actions

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

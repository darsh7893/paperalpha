"""Paper trading execution engine. No real orders — virtual cash only."""
import time
from . import db
from .data import get_price

MAX_POSITION_PCT = 0.20   # max 20% of equity per symbol
MIN_CASH_RESERVE = 500.0

def equity(uid):
    cash = db.get_cash(uid)
    total = cash
    for p in db.get_positions(uid):
        px = get_price(p["symbol"]) or p["avg_price"]
        total += p["qty"] * px
    return total, cash

def buy(uid, symbol, usd_amount, bot, reason):
    price = get_price(symbol)
    if not price:
        return {"ok": False, "error": "no price"}
    eq, cash = equity(uid)
    usd_amount = min(usd_amount, eq * MAX_POSITION_PCT, cash - MIN_CASH_RESERVE)
    if usd_amount < 10:
        return {"ok": False, "error": "insufficient cash / too small"}
    qty = round(usd_amount / price, 4)
    cost = qty * price
    pos = db.get_position(uid, symbol)
    new_qty = pos["qty"] + qty
    avg = (pos["qty"] * pos["avg_price"] + cost) / new_qty if new_qty else 0
    db.set_cash(uid, cash - cost)
    db.upsert_position(uid, symbol, new_qty, avg)
    db.log_trade(uid, time.time(), symbol, "buy", qty, price, bot, reason)
    return {"ok": True, "qty": qty, "price": price}

def sell(uid, symbol, qty=None, bot="manual", reason="manual sell"):
    price = get_price(symbol)
    if not price:
        return {"ok": False, "error": "no price"}
    pos = db.get_position(uid, symbol)
    if pos["qty"] <= 0:
        return {"ok": False, "error": "no position"}
    qty = pos["qty"] if qty is None else min(qty, pos["qty"])
    proceeds = qty * price
    pnl = (price - pos["avg_price"]) * qty
    cash = db.get_cash(uid)
    db.set_cash(uid, cash + proceeds)
    db.upsert_position(uid, symbol, pos["qty"] - qty, pos["avg_price"])
    db.log_trade(uid, time.time(), symbol, "sell", qty, price, bot, reason, pnl)
    db.update_bot_stats(bot, pnl > 0, pnl)
    return {"ok": True, "qty": qty, "price": price, "pnl": round(pnl, 2)}

def sell_all(uid, bot="manual", reason="sell all"):
    return [sell(uid, p["symbol"], bot=bot, reason=reason) for p in db.get_positions(uid)]

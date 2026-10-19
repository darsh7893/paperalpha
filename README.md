# PaperAlpha — AI Paper Trading Platform

Mobile-first paper trading platform with learning AI bots. **No real money. Virtual $100,000.**

## What it does
- 📱 Mobile-friendly web app (installable PWA — use from your phone browser)
- 🔐 Login + multi-user: everyone who signs up gets their own virtual $100,000. First signup is admin.
- 🤖 3 bots that paper-trade automatically (per user, toggleable in the app):
  - **News Sentiment Bot** — reads headlines, scores sentiment, bets on momentum
  - **Momentum Bot** — SMA crossover + RSI strategy
  - **Ensemble Learner** — tracks which bot/params win, shifts capital to winners over time (it *learns*)
- 📊 Live-ish prices (free Yahoo Finance), portfolio dashboard, trade history
- 🧪 100% paper trading — no broker, no real orders

## What "AI" is actually in here (no API keys needed)
- **News bot:** VADER, a small NLP sentiment model running locally — scores headlines −1…+1. No LLM, no API.
- **Momentum bot:** not AI at all — pure math (moving averages + RSI).
- **Learner:** genuine online machine learning — an epsilon-greedy multi-armed bandit that reallocates
  capital toward whichever bot actually makes money, plus tiny evolutionary mutations of the loser's
  parameters. It learns from experience, not from pretraining.
- Not in here (yet): LLM reasoning / deep-learning price prediction. A Groq free-tier "analyst agent"
  that writes a rationale per trade would be the natural next upgrade — the engine is already modular for it.

## Free alternatives in the market
| Tool | Free? | What it is |
|---|---|---|
| **Alpaca** | Yes (paper trading free) | Commission-free API brokerage, unlimited virtual cash. Best if you later go live. You bring the AI. |
| **Freqtrade** | 100% open source | Python crypto bot, backtesting + paper + ML hyperopt. Steep learning curve. |
| **Hummingbot** | 100% open source | Market-making / arbitrage framework, 50+ exchanges. |
| **OctoBot** | 100% open source | Community AI trading bot with web UI. |
| **QuantConnect** | Free tier | Cloud backtesting + Alpaca integration. |

None of them does "news sentiment + self-improving ensemble" out of the box for free — that's what PaperAlpha adds.

## Quick start (local)
```bash
pip install -r requirements.txt
python -m backend.app
# open http://localhost:8000
```

## Run bots
```bash
python bot_runner.py --once      # single cycle (test)
python bot_runner.py              # loop every 15 min
```

## Deploy live (free)
- **Render:** connect repo → New Web Service → `render.yaml` handles it
- **Railway / Fly.io:** `Dockerfile` included
- Then open the URL on your phone → Add to Home Screen → it behaves like an app

## Persistence (important!)
Render's free tier wipes the local filesystem on every redeploy — without this,
every account, trade, and the bots' learning would be deleted on each deploy.
Set these two env vars (Render dashboard → service → Environment) to use a free
Turso cloud database instead (accounts then survive redeploys forever):

1. Sign up at turso.tech (GitHub login), create a database called `paperalpha`
2. On the database page → Connect → copy the database URL (`libsql://...`)
3. Create an auth token for the database and copy it
4. In Render: add `TURSO_URL` = the database URL, `TURSO_AUTH_TOKEN` = the token
5. Save (triggers a redeploy). Sign up fresh once in the app — that account now persists.

Without these vars the app falls back to a local SQLite file (fine for local dev).

## How the learning works
1. Every bot decision + outcome is logged to SQLite (`trades.db`)
2. `learner.py` scores each strategy on rolling 7-day Sharpe / win-rate
3. Capital allocation rebalances toward winners (epsilon-greedy bandit)
4. Losing params get mutated slightly (tiny evolutionary step)
5. Over weeks, the ensemble drifts toward what actually worked *in your paper market*

## Disclaimer
Educational project. Not financial advice. Paper trading only — this app cannot place real orders.

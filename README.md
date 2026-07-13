# Aura FX

Swing/day trade Telegram signal bot for EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD.
Rules-based market structure engine (BOS/CHoCH) drives entries, exits, and the
"why" behind every message. Same architectural pattern as AURUM/CIPHER/TITAN:
Python bot → Railway → Telegram, Twelve Data as the price feed.

## What's built

- **`config.py`** — pairs, timeframes, R:R targets, credit budget notes
- **`twelvedata_client.py`** — OHLCV fetching with a daily credit counter (hard stop
  before hitting your 800/day limit, cap set to 780 as a safety buffer)
- **`structure_engine.py`** — fractal swing detection, trend classification,
  BOS/CHoCH labeling with plain-English reasoning strings
- **`trade_manager.py`** — entry generation (BOS aligned with D1 trend), SQLite
  trade log, monitoring for TP1/TP2/TP3 (partial closes + break-even SL after TP1),
  SL hits, and structure-shift closes
- **`telegram_bot.py`** — message formatting for entries, TP/SL hits, structure
  closes, daily/weekly reports
- **`reports.py`** — daily (22:00) and weekly (Friday 22:00) report generation
- **`main.py`** — APScheduler orchestration: D1 refresh 1x/day, H4 check every 4h,
  H1 check + monitoring every hour, reports on schedule
- **`ml_filter.py`** — stub, disabled by default (see below)

## Credit budget (Twelve Data, 800/day)

| Job | Pairs | Frequency | Calls/day |
|---|---|---|---|
| D1 trend | 5 | 1x | 5 |
| H4 structure | 5 | 6x (every 4h) | 30 |
| H1 structure + monitoring | 5 | 24x (hourly) | 120 |
| **Total** | | | **~155/day** |

Plenty of headroom under 800 — room to add a 6th pair, tighten to 30-min
checks on H1, or add retry logic without risk of hitting the ceiling. The
client also self-throttles: if usage nears the cap it skips remaining calls
for that run rather than erroring out mid-loop.

## Setup

```bash
cp .env.example .env
# fill in TWELVEDATA_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
pip install -r requirements.txt
python main.py
```

## Deploy to Railway

Same flow as TITAN/AURUM: push to GitHub, connect the repo in Railway, set the
three env vars in the Railway dashboard, deploy. `main.py` runs as a long-lived
worker (no web server needed) — set the Railway start command to `python main.py`.

---

## Leftover work (things I deliberately didn't build yet)

**1. Persistent database.** SQLite (`aura_fx.db`) works fine locally, but
Railway's filesystem is ephemeral — a redeploy wipes it and you lose trade
history mid-week. Before going live, swap `DATABASE_URL` to a Railway Postgres
add-on. The `trade_manager.py` functions are simple enough to port to
`psycopg2`/SQLAlchemy in an hour or so.

**2. ML confluence filter is a stub.** I built the hook (`ml_filter.py`,
`ML_FILTER_ENABLED` flag) but didn't train a model. Reason: it needs a labeled
dataset of past BOS setups with win/loss outcomes, which doesn't exist yet for
swing timeframes. Two ways to get there:
   - Run the bot signal-only for 4-6 weeks, log outcomes, then train on that
   - Or adapt AURUM's feature engineering pipeline to D1/H4/H1 features and
     backtest against historical Twelve Data candles first

Until then the bot runs on pure structure rules — fully explainable, just
without the extra ML edge AURUM has.

**3. No backtest yet.** The structure engine has only been sanity-checked
against synthetic data (confirmed it correctly flags trend + CHoCH on a
constructed reversal). It hasn't been run against real historical EUR/USD/GBP/USD/etc.
data to see how often BOS signals actually work out. I'd strongly recommend
backtesting before risking real capital — happy to build a backtest script
next that replays historical candles through `structure_engine.py` and reports
win rate / R multiple by pair.

**4. Position sizing isn't handled.** Trades track R-multiples (risk-adjusted),
not lot sizes or account %. If you want the bot to suggest lot size based on
account balance and % risk per trade, that's a small addition to `trade_manager.py`.

**5. Swing point noise filtering is basic.** `MIN_SWING_PCT` in config.py filters
out tiny swings, but it's a flat threshold — during low-volatility weeks
(holidays, summer lull) it may over-filter; during high-volatility news weeks
it may under-filter. Worth tuning per pair once you see it running live, or
switching to an ATR-relative threshold instead of a flat percentage.

**6. No manual override commands.** Right now it's a one-way broadcast (bot →
Telegram channel). If you want to be able to message the bot to manually close
a trade, pause a pair, or check status on demand, that needs a Telegram
webhook/polling listener added — separate from the scheduled push messages.

**7. No dashboard.** TITAN has a Vercel-hosted HTML dashboard; Aura FX doesn't
have one yet. Straightforward to add once the SQLite→Postgres move is done,
since the dashboard would read the same trades table.

**8. Branding/naming not done.** No logo, color scheme, or channel branding
built yet — happy to do a quick identity pass (like TITAN's Spartan helmet)
once the bot's logic is proven out.

### Suggested next step
Run it signal-only (comment out real entries, just log what *would* have
triggered) for a week or two against live data, sanity-check the BOS/CHoCH
calls against what you'd read on a chart yourself, then move to the backtest
before switching on real trade generation.

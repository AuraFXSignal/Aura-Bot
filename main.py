"""
Aura FX - Main orchestrator
Runs on Railway as a long-lived process. Schedules:
- D1 trend context refresh (1x/day)
- H4 structure checks (every 4h)
- H1 structure checks + entry generation + trade monitoring (every 1h)
- Daily report (22:00) / Weekly report (Fri 22:00)
"""
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from config import (
    PAIRS, TF_DAILY, TF_H4, TF_H1,
    REPORT_TIMEZONE, DAILY_REPORT_HOUR, WEEKLY_REPORT_DAY, WEEKLY_REPORT_HOUR,
)
import twelvedata_client as td
from structure_engine import build_structure_state
import trade_manager
import reports
import telegram_bot

# Cache of latest daily-trend state per pair, used to bias H1/H4 signals
_daily_trend_cache = {}


def job_refresh_daily_trend():
    print("[main] Refreshing D1 trend context...")
    for pair in PAIRS:
        try:
            df = td.fetch_ohlcv(pair, TF_DAILY, outputsize=100)
            state = build_structure_state(df, pair)
            _daily_trend_cache[pair] = state.trend
            print(f"  {pair}: D1 trend = {state.trend}")
        except td.CreditLimitError as e:
            print(f"  [SKIPPED - credit cap] {e}")
            break
        except Exception as e:
            print(f"  [ERROR] {pair} D1: {e}")


def job_h4_structure_check():
    print("[main] Running H4 structure check...")
    for pair in PAIRS:
        try:
            df = td.fetch_ohlcv(pair, TF_H4, outputsize=150)
            state = build_structure_state(df, pair)
            if state.last_event and state.last_event.kind == "CHoCH":
                event = state.last_event
                swing_key = event.broken_swing.datetime if event.broken_swing else "none"
                signature = f"{event.kind}:{event.direction}:{round(event.broken_level, 5)}:{swing_key}"
                last_signature = trade_manager.get_last_alert_signature(pair, "H4")
                if signature != last_signature:
                    telegram_bot.send_message(f"🔎 *H4 CHoCH detected*\n{event.reason}")
                    trade_manager.set_last_alert_signature(pair, "H4", signature)
                else:
                    print(f"  {pair}: CHoCH unchanged since last alert — skipping duplicate message")
        except td.CreditLimitError as e:
            print(f"  [SKIPPED - credit cap] {e}")
            break
        except Exception as e:
            print(f"  [ERROR] {pair} H4: {e}")


def job_h1_check_and_monitor():
    print("[main] Running H1 structure check + trade monitoring...")
    open_trades = trade_manager.get_open_trades()
    open_pairs = {t.pair for t in open_trades}

    for pair in PAIRS:
        try:
            df = td.fetch_ohlcv(pair, TF_H1, outputsize=150)
        except td.CreditLimitError as e:
            print(f"  [SKIPPED - credit cap] {e}")
            break
        except Exception as e:
            print(f"  [ERROR] {pair} H1: {e}")
            continue

        state = build_structure_state(df, pair)
        current_price = df["close"].iloc[-1]

        # Monitor any open trade on this pair
        for trade in [t for t in open_trades if t.pair == pair]:
            trade_manager.monitor_trade(trade, current_price, state)

        # Only look for new entries if daily trend agrees with H1 BOS direction
        # and there isn't already an open trade on this pair.
        daily_trend = _daily_trend_cache.get(pair, "ranging")
        if pair not in open_pairs and state.last_event and state.last_event.kind == "BOS":
            if (daily_trend == "bullish" and state.last_event.direction == "bullish") or \
               (daily_trend == "bearish" and state.last_event.direction == "bearish"):
                trade_manager.generate_entry(pair, state, current_price)


def main():
    trade_manager.init_db()
    tz = pytz.timezone(REPORT_TIMEZONE)
    scheduler = BlockingScheduler(timezone=tz)

    scheduler.add_job(job_refresh_daily_trend, CronTrigger(hour=1, minute=0))
    scheduler.add_job(job_h4_structure_check, CronTrigger(hour="1,5,9,13,17,21", minute=5))
    scheduler.add_job(job_h1_check_and_monitor, CronTrigger(minute=5))  # every hour at :05
    scheduler.add_job(reports.send_daily_report, CronTrigger(hour=DAILY_REPORT_HOUR, minute=0))
    scheduler.add_job(
        reports.send_weekly_report,
        CronTrigger(day_of_week=WEEKLY_REPORT_DAY, hour=WEEKLY_REPORT_HOUR, minute=0),
    )

    print("[main] Aura FX started. Running initial daily trend fetch...")
    job_refresh_daily_trend()

    print("[main] Scheduler running.")
    scheduler.start()


if __name__ == "__main__":
    main()

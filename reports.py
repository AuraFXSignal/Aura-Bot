"""
Aura FX - Daily/Weekly report generation
"""
from datetime import datetime, timedelta
import trade_manager
import telegram_bot


def build_daily_report() -> dict:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    closed_today = trade_manager.get_trades_closed_since(today_start.isoformat())
    wins = [t for t in closed_today if (t.result_r or 0) > 0]
    losses = [t for t in closed_today if (t.result_r or 0) <= 0]
    open_trades = trade_manager.get_open_trades()

    win_rate = (len(wins) / len(closed_today) * 100) if closed_today else 0.0
    net_r = sum(t.result_r or 0 for t in closed_today)

    return {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "open_count": len(open_trades),
        "closed_today": len(closed_today),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "net_r": net_r,
    }


def build_weekly_report() -> dict:
    week_ago = datetime.utcnow() - timedelta(days=7)
    closed = trade_manager.get_trades_closed_since(week_ago.isoformat())
    wins = [t for t in closed if (t.result_r or 0) > 0]
    losses = [t for t in closed if (t.result_r or 0) <= 0]
    win_rate = (len(wins) / len(closed) * 100) if closed else 0.0
    net_r = sum(t.result_r or 0 for t in closed)

    pair_r = {}
    for t in closed:
        pair_r.setdefault(t.pair, 0)
        pair_r[t.pair] += t.result_r or 0
    best_pair = max(pair_r, key=pair_r.get) if pair_r else "N/A"
    worst_pair = min(pair_r, key=pair_r.get) if pair_r else "N/A"

    return {
        "week_ending": datetime.utcnow().strftime("%Y-%m-%d"),
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "net_r": net_r,
        "best_pair": best_pair,
        "worst_pair": worst_pair,
    }


def send_daily_report():
    report = build_daily_report()
    telegram_bot.send_message(telegram_bot.format_daily_report(report))


def send_weekly_report():
    report = build_weekly_report()
    telegram_bot.send_message(telegram_bot.format_weekly_report(report))

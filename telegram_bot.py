"""
Aura FX - Telegram messaging
Sends entry, TP/SL, structure-shift-close, and report messages.
"""
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"


def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[telegram_bot] Missing bot token/chat id — message not sent:\n", text)
        return False
    try:
        resp = requests.post(
            API_URL,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[telegram_bot] Failed to send message: {e}")
        return False


def format_entry(trade) -> str:
    return (
        f"🟢 *AURA FX — New {trade.direction.upper()} Signal*\n\n"
        f"*Pair:* {trade.pair}\n"
        f"*Entry:* {trade.entry:.5f}\n"
        f"*SL:* {trade.sl:.5f}\n"
        f"*TP1:* {trade.tp1:.5f}\n"
        f"*TP2:* {trade.tp2:.5f}\n"
        f"*TP3:* {trade.tp3:.5f}\n\n"
        f"*Why:* {trade.reason}"
    )


def format_tp_hit(trade, tp_level: str, price: float) -> str:
    return (
        f"✅ *AURA FX — {trade.pair} {tp_level} Hit*\n"
        f"Price: {price:.5f}\n"
        f"Direction: {trade.direction.upper()}"
    )


def format_sl_hit(trade, price: float) -> str:
    return (
        f"🔴 *AURA FX — {trade.pair} SL Hit*\n"
        f"Price: {price:.5f}\n"
        f"Direction: {trade.direction.upper()}"
    )


def format_structure_close(trade, event) -> str:
    return (
        f"⚠️ *AURA FX — {trade.pair} Closed: Structure Shift*\n\n"
        f"{event.reason}\n\n"
        f"Trade closed early to protect gains/limit loss."
    )


def format_daily_report(report: dict) -> str:
    lines = [f"📊 *Aura FX — Daily Report ({report['date']})*", ""]
    lines.append(f"Open trades: {report['open_count']}")
    lines.append(f"Closed today: {report['closed_today']}")
    lines.append(f"Wins: {report['wins']} | Losses: {report['losses']}")
    lines.append(f"Win rate: {report['win_rate']:.1f}%")
    lines.append(f"Net R: {report['net_r']:+.2f}R")
    return "\n".join(lines)


def format_weekly_report(report: dict) -> str:
    lines = [f"📈 *Aura FX — Weekly Report (w/e {report['week_ending']})*", ""]
    lines.append(f"Total trades: {report['total_trades']}")
    lines.append(f"Wins: {report['wins']} | Losses: {report['losses']}")
    lines.append(f"Win rate: {report['win_rate']:.1f}%")
    lines.append(f"Net R: {report['net_r']:+.2f}R")
    lines.append(f"Best pair: {report['best_pair']}")
    lines.append(f"Worst pair: {report['worst_pair']}")
    return "\n".join(lines)

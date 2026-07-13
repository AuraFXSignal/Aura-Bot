"""
Aura FX - Trade Manager
Generates entries from structure state, tracks open trades, monitors for
TP/SL hits and structure-shift invalidation, persists trade history.
"""
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List

from config import (
    RISK_REWARD_TP1, RISK_REWARD_TP2, RISK_REWARD_TP3,
    PARTIAL_CLOSE_TP1_PCT, PARTIAL_CLOSE_TP2_PCT, MOVE_SL_TO_BE_AFTER_TP1,
)
from structure_engine import StructureState, StructureEvent, is_structure_invalidated
import telegram_bot

DB_PATH = "aura_fx.db"  # NOTE: ephemeral on Railway redeploy — see README "Leftover"


@dataclass
class Trade:
    id: Optional[int]
    pair: str
    direction: str  # "long" or "short"
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    status: str  # "open", "closed_tp", "closed_sl", "closed_structure"
    reason: str
    opened_at: str
    closed_at: Optional[str] = None
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    result_r: Optional[float] = None


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT, direction TEXT, entry REAL, sl REAL,
            tp1 REAL, tp2 REAL, tp3 REAL, status TEXT, reason TEXT,
            opened_at TEXT, closed_at TEXT,
            tp1_hit INTEGER DEFAULT 0, tp2_hit INTEGER DEFAULT 0, tp3_hit INTEGER DEFAULT 0,
            result_r REAL
        )
    """)
    conn.commit()
    conn.close()


def _row_to_trade(row) -> Trade:
    return Trade(
        id=row[0], pair=row[1], direction=row[2], entry=row[3], sl=row[4],
        tp1=row[5], tp2=row[6], tp3=row[7], status=row[8], reason=row[9],
        opened_at=row[10], closed_at=row[11],
        tp1_hit=bool(row[12]), tp2_hit=bool(row[13]), tp3_hit=bool(row[14]),
        result_r=row[15],
    )


def save_trade(trade: Trade) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("""
        INSERT INTO trades (pair, direction, entry, sl, tp1, tp2, tp3, status, reason,
                             opened_at, closed_at, tp1_hit, tp2_hit, tp3_hit, result_r)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (trade.pair, trade.direction, trade.entry, trade.sl, trade.tp1, trade.tp2, trade.tp3,
          trade.status, trade.reason, trade.opened_at, trade.closed_at,
          int(trade.tp1_hit), int(trade.tp2_hit), int(trade.tp3_hit), trade.result_r))
    conn.commit()
    trade_id = cur.lastrowid
    conn.close()
    return trade_id


def update_trade(trade: Trade):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE trades SET status=?, closed_at=?, tp1_hit=?, tp2_hit=?, tp3_hit=?, result_r=?
        WHERE id=?
    """, (trade.status, trade.closed_at, int(trade.tp1_hit), int(trade.tp2_hit),
          int(trade.tp3_hit), trade.result_r, trade.id))
    conn.commit()
    conn.close()


def get_open_trades() -> List[Trade]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT * FROM trades WHERE status='open'").fetchall()
    conn.close()
    return [_row_to_trade(r) for r in rows]


def get_trades_since(iso_datetime: str) -> List[Trade]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT * FROM trades WHERE opened_at >= ?", (iso_datetime,)).fetchall()
    conn.close()
    return [_row_to_trade(r) for r in rows]


# --- Entry generation ---

def generate_entry(pair: str, state: StructureState, current_price: float) -> Optional[Trade]:
    """
    Called after an H1 structure check confirms a BOS aligned with the
    higher-timeframe trend. Builds a trade with SL beyond the invalidation
    swing and TPs at fixed R multiples.
    """
    event = state.last_event
    if event is None or event.kind != "BOS":
        return None  # only trade continuation BOS, not raw CHoCH (too early/risky)

    direction = "long" if event.direction == "bullish" else "short"
    entry = current_price

    if direction == "long":
        sl = state.key_low if state.key_low else entry * 0.995
        risk = entry - sl
        tp1 = entry + risk * RISK_REWARD_TP1
        tp2 = entry + risk * RISK_REWARD_TP2
        tp3 = entry + risk * RISK_REWARD_TP3
    else:
        sl = state.key_high if state.key_high else entry * 1.005
        risk = sl - entry
        tp1 = entry - risk * RISK_REWARD_TP1
        tp2 = entry - risk * RISK_REWARD_TP2
        tp3 = entry - risk * RISK_REWARD_TP3

    if risk <= 0:
        return None  # bad geometry, skip

    trade = Trade(
        id=None, pair=pair, direction=direction, entry=entry, sl=sl,
        tp1=tp1, tp2=tp2, tp3=tp3, status="open", reason=event.reason,
        opened_at=datetime.utcnow().isoformat(),
    )
    trade.id = save_trade(trade)
    telegram_bot.send_message(telegram_bot.format_entry(trade))
    return trade


# --- Monitoring ---

def monitor_trade(trade: Trade, current_price: float, state: Optional[StructureState] = None):
    """
    Check one open trade against current price for TP/SL hits, and against
    the latest structure state for an invalidation close.
    """
    if trade.status != "open":
        return

    # Structure-shift check first (can pre-empt a slower-moving SL)
    if state is not None:
        invalidation = is_structure_invalidated(state, trade.direction)
        if invalidation:
            trade.status = "closed_structure"
            trade.closed_at = datetime.utcnow().isoformat()
            trade.result_r = _partial_r(trade, current_price)
            update_trade(trade)
            telegram_bot.send_message(telegram_bot.format_structure_close(trade, invalidation))
            return

    if trade.direction == "long":
        if not trade.tp1_hit and current_price >= trade.tp1:
            trade.tp1_hit = True
            if MOVE_SL_TO_BE_AFTER_TP1:
                trade.sl = trade.entry
            update_trade(trade)
            telegram_bot.send_message(telegram_bot.format_tp_hit(trade, "TP1", current_price))
        if trade.tp1_hit and not trade.tp2_hit and current_price >= trade.tp2:
            trade.tp2_hit = True
            update_trade(trade)
            telegram_bot.send_message(telegram_bot.format_tp_hit(trade, "TP2", current_price))
        if trade.tp2_hit and not trade.tp3_hit and current_price >= trade.tp3:
            trade.tp3_hit = True
            trade.status = "closed_tp"
            trade.closed_at = datetime.utcnow().isoformat()
            trade.result_r = RISK_REWARD_TP3
            update_trade(trade)
            telegram_bot.send_message(telegram_bot.format_tp_hit(trade, "TP3 (Final)", current_price))
        elif current_price <= trade.sl:
            trade.status = "closed_sl"
            trade.closed_at = datetime.utcnow().isoformat()
            trade.result_r = _partial_r(trade, current_price)
            update_trade(trade)
            telegram_bot.send_message(telegram_bot.format_sl_hit(trade, current_price))
    else:  # short
        if not trade.tp1_hit and current_price <= trade.tp1:
            trade.tp1_hit = True
            if MOVE_SL_TO_BE_AFTER_TP1:
                trade.sl = trade.entry
            update_trade(trade)
            telegram_bot.send_message(telegram_bot.format_tp_hit(trade, "TP1", current_price))
        if trade.tp1_hit and not trade.tp2_hit and current_price <= trade.tp2:
            trade.tp2_hit = True
            update_trade(trade)
            telegram_bot.send_message(telegram_bot.format_tp_hit(trade, "TP2", current_price))
        if trade.tp2_hit and not trade.tp3_hit and current_price <= trade.tp3:
            trade.tp3_hit = True
            trade.status = "closed_tp"
            trade.closed_at = datetime.utcnow().isoformat()
            trade.result_r = RISK_REWARD_TP3
            update_trade(trade)
            telegram_bot.send_message(telegram_bot.format_tp_hit(trade, "TP3 (Final)", current_price))
        elif current_price >= trade.sl:
            trade.status = "closed_sl"
            trade.closed_at = datetime.utcnow().isoformat()
            trade.result_r = _partial_r(trade, current_price)
            update_trade(trade)
            telegram_bot.send_message(telegram_bot.format_sl_hit(trade, current_price))


def _partial_r(trade: Trade, exit_price: float) -> float:
    """Approximate realised R accounting for partial closes already taken."""
    risk = abs(trade.entry - trade.sl) if trade.sl != trade.entry else abs(trade.tp1 - trade.entry) / RISK_REWARD_TP1
    if risk == 0:
        return 0.0
    realised = 0.0
    remaining_pct = 100
    if trade.tp1_hit:
        realised += (PARTIAL_CLOSE_TP1_PCT / 100) * RISK_REWARD_TP1
        remaining_pct -= PARTIAL_CLOSE_TP1_PCT
    if trade.tp2_hit:
        realised += (PARTIAL_CLOSE_TP2_PCT / 100) * RISK_REWARD_TP2
        remaining_pct -= PARTIAL_CLOSE_TP2_PCT
    final_move = (exit_price - trade.entry) / risk if trade.direction == "long" else (trade.entry - exit_price) / risk
    realised += (remaining_pct / 100) * final_move
    return round(realised, 2)

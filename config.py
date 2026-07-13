"""
Aura FX - Configuration
Swing/day trade signal bot for major FX pairs.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys / Secrets (set these in .env or Railway variables) ---
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Pairs ---
PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD"]

# --- Timeframes ---
TF_DAILY = "1day"
TF_H4 = "4h"
TF_H1 = "1h"

# --- Swing structure detection ---
SWING_LOOKBACK = 5          # bars each side to confirm a fractal swing point
MIN_SWING_PCT = 0.0005      # minimum % move to count as a valid swing (filters noise), tune per pair

# --- Trade management ---
RISK_REWARD_TP1 = 1.0       # TP1 at 1R
RISK_REWARD_TP2 = 2.0       # TP2 at 2R
RISK_REWARD_TP3 = 3.5       # TP3 at 3.5R (runner)
PARTIAL_CLOSE_TP1_PCT = 50  # close 50% at TP1
PARTIAL_CLOSE_TP2_PCT = 30  # close another 30% at TP2, rest rides to TP3/trail
MOVE_SL_TO_BE_AFTER_TP1 = True

# --- ML confluence filter ---
ML_FILTER_ENABLED = False   # flip on once a trained model + threshold is validated (see README "Leftover")
ML_CONFLUENCE_THRESHOLD = 0.60

# --- Twelve Data credit budget (800/day free tier assumption) ---
# Daily (D1):  5 pairs x 1 call/day               = 5
# H4 checks:   5 pairs x 6 calls/day (every 4h)    = 30
# H1 checks:   5 pairs x 24 calls/day (every 1h)   = 120
# Total ~155/day, well within 800 limit.
API_CALL_LOG_PATH = "logs/api_calls.log"

# --- Reporting ---
REPORT_TIMEZONE = "Europe/London"
DAILY_REPORT_HOUR = 22   # 22:00 local, after NY close
WEEKLY_REPORT_DAY = "fri"
WEEKLY_REPORT_HOUR = 22

# --- Storage ---
# NOTE: SQLite file works locally but Railway's filesystem is ephemeral on redeploy.
# For production, point DATABASE_URL at a Railway Postgres add-on (see README "Leftover").
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///aura_fx.db")

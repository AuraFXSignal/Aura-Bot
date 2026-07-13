"""
Aura FX - Twelve Data client
Fetches OHLCV candles and tracks daily API credit usage so we never
blow past the plan limit.
"""
import requests
import pandas as pd
from datetime import datetime, date
import json
import os

from config import TWELVEDATA_API_KEY, API_CALL_LOG_PATH

BASE_URL = "https://api.twelvedata.com/time_series"

_usage_cache = {"date": None, "count": 0}


def _load_usage():
    global _usage_cache
    today = str(date.today())
    if os.path.exists(API_CALL_LOG_PATH):
        with open(API_CALL_LOG_PATH, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
        if data.get("date") == today:
            _usage_cache = data
            return
    _usage_cache = {"date": today, "count": 0}


def _save_usage():
    os.makedirs(os.path.dirname(API_CALL_LOG_PATH), exist_ok=True)
    with open(API_CALL_LOG_PATH, "w") as f:
        json.dump(_usage_cache, f)


def get_daily_usage() -> int:
    _load_usage()
    return _usage_cache["count"]


def _record_call(n=1):
    _load_usage()
    _usage_cache["count"] += n
    _save_usage()


class CreditLimitError(Exception):
    pass


def fetch_ohlcv(symbol: str, interval: str, outputsize: int = 100, daily_cap: int = 780) -> pd.DataFrame:
    """
    Fetch OHLCV candles for a symbol/interval.
    Raises CreditLimitError if today's usage would exceed daily_cap
    (kept a little under the true 800 limit as a safety buffer).
    """
    if get_daily_usage() >= daily_cap:
        raise CreditLimitError(
            f"Daily Twelve Data credit cap ({daily_cap}) reached — skipping call for {symbol} {interval}"
        )

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVEDATA_API_KEY,
        "format": "JSON",
    }
    resp = requests.get(BASE_URL, params=params, timeout=15)
    _record_call(1)
    resp.raise_for_status()
    data = resp.json()

    if "values" not in data:
        raise ValueError(f"Twelve Data error for {symbol} {interval}: {data}")

    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


def fetch_multi(symbols: list, interval: str, outputsize: int = 100) -> dict:
    """
    Fetch several symbols for one interval. Twelve Data supports comma-joined
    symbols in a single call on paid plans — falls back to individual calls
    here for safety/compatibility with the free tier.
    """
    out = {}
    for sym in symbols:
        try:
            out[sym] = fetch_ohlcv(sym, interval, outputsize)
        except CreditLimitError:
            raise
        except Exception as e:
            print(f"[twelvedata_client] Failed to fetch {sym} {interval}: {e}")
    return out

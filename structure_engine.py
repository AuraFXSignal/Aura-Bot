"""
Aura FX - Market Structure Engine

Rules-based swing detection and BOS/CHoCH labeling. This produces the
human-readable "why" behind every entry, close, and structure-shift alert.

Definitions used:
- Swing high: a candle whose high is the highest within `lookback` bars on
  either side (fractal method).
- Swing low: a candle whose low is the lowest within `lookback` bars on
  either side.
- Uptrend: sequence of higher highs (HH) and higher lows (HL).
- Downtrend: sequence of lower highs (LH) and lower lows (LL).
- BOS (Break of Structure): price breaks the most recent swing point IN THE
  DIRECTION of the current trend -> trend continuation confirmation.
- CHoCH (Change of Character): price breaks the most recent swing point
  AGAINST the current trend -> first signal of a potential reversal.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Literal
import pandas as pd

from config import SWING_LOOKBACK, MIN_SWING_PCT

TrendState = Literal["bullish", "bearish", "ranging"]


@dataclass
class SwingPoint:
    index: int
    datetime: pd.Timestamp
    price: float
    kind: Literal["high", "low"]


@dataclass
class StructureEvent:
    kind: Literal["BOS", "CHoCH"]
    direction: Literal["bullish", "bearish"]
    broken_level: float
    broken_swing: SwingPoint
    at_datetime: pd.Timestamp
    at_price: float
    reason: str


@dataclass
class StructureState:
    trend: TrendState
    swings: List[SwingPoint]
    last_event: Optional[StructureEvent] = None
    key_high: Optional[float] = None   # most recent unbroken swing high
    key_low: Optional[float] = None    # most recent unbroken swing low
    history: List[StructureEvent] = field(default_factory=list)


def find_swings(df: pd.DataFrame, lookback: int = SWING_LOOKBACK) -> List[SwingPoint]:
    """Fractal swing detection over a candle dataframe (needs 'high','low','datetime')."""
    swings = []
    n = len(df)
    for i in range(lookback, n - lookback):
        window_high = df["high"].iloc[i - lookback: i + lookback + 1]
        window_low = df["low"].iloc[i - lookback: i + lookback + 1]

        if df["high"].iloc[i] == window_high.max() and df["high"].iloc[i] > window_high.drop(df.index[i]).max():
            swings.append(SwingPoint(i, df["datetime"].iloc[i], df["high"].iloc[i], "high"))
        elif df["low"].iloc[i] == window_low.min() and df["low"].iloc[i] < window_low.drop(df.index[i]).min():
            swings.append(SwingPoint(i, df["datetime"].iloc[i], df["low"].iloc[i], "low"))

    # Filter out noise: consecutive same-kind swings, keep the most extreme
    cleaned: List[SwingPoint] = []
    for s in swings:
        if cleaned and cleaned[-1].kind == s.kind:
            if s.kind == "high" and s.price > cleaned[-1].price:
                cleaned[-1] = s
            elif s.kind == "low" and s.price < cleaned[-1].price:
                cleaned[-1] = s
        else:
            cleaned.append(s)
    return cleaned


def _pct_move(a: float, b: float) -> float:
    return abs(a - b) / b if b else 0


def build_structure_state(df: pd.DataFrame, pair: str, lookback: int = SWING_LOOKBACK) -> StructureState:
    """
    Walk through confirmed swings in order and derive current trend +
    the most recent BOS/CHoCH event, with a plain-English reason string
    ready to drop straight into a Telegram message.
    """
    swings = find_swings(df, lookback)
    swings = [s for s in swings if _pct_move(
        s.price, swings[swings.index(s) - 1].price if swings.index(s) > 0 else s.price
    ) >= MIN_SWING_PCT or swings.index(s) == 0]

    state = StructureState(trend="ranging", swings=swings)
    if len(swings) < 4:
        return state  # not enough structure yet

    trend: TrendState = "ranging"
    key_high, key_low = None, None
    last_confirmed_high, last_confirmed_low = None, None

    for s in swings:
        if s.kind == "high":
            if last_confirmed_high is None:
                last_confirmed_high = s
            else:
                if s.price > last_confirmed_high.price:
                    # higher high
                    if trend == "bearish":
                        # potential CHoCH -> now check confirmation via low structure below
                        pass
                    trend = "bullish" if trend != "bearish" else trend
                last_confirmed_high = s
            key_high = s.price
        else:  # low
            if last_confirmed_low is None:
                last_confirmed_low = s
            else:
                if s.price < last_confirmed_low.price:
                    trend = "bearish" if trend != "bullish" else trend
                last_confirmed_low = s
            key_low = s.price

    # Determine BOS/CHoCH based on latest close vs latest untested swing point
    last_close = df["close"].iloc[-1]
    last_dt = df["datetime"].iloc[-1]
    event = None

    if trend == "bullish" and key_high is not None and last_close > key_high:
        event = StructureEvent(
            kind="BOS", direction="bullish", broken_level=key_high,
            broken_swing=last_confirmed_high, at_datetime=last_dt, at_price=last_close,
            reason=f"{pair}: bullish BOS — price closed above prior swing high at {key_high:.5f}, "
                   f"confirming trend continuation."
        )
    elif trend == "bearish" and key_low is not None and last_close < key_low:
        event = StructureEvent(
            kind="BOS", direction="bearish", broken_level=key_low,
            broken_swing=last_confirmed_low, at_datetime=last_dt, at_price=last_close,
            reason=f"{pair}: bearish BOS — price closed below prior swing low at {key_low:.5f}, "
                   f"confirming trend continuation."
        )
    elif trend == "bullish" and key_low is not None and last_close < key_low:
        event = StructureEvent(
            kind="CHoCH", direction="bearish", broken_level=key_low,
            broken_swing=last_confirmed_low, at_datetime=last_dt, at_price=last_close,
            reason=f"{pair}: bearish CHoCH — price broke below the last higher low at {key_low:.5f}, "
                   f"first sign the uptrend may be reversing."
        )
    elif trend == "bearish" and key_high is not None and last_close > key_high:
        event = StructureEvent(
            kind="CHoCH", direction="bullish", broken_level=key_high,
            broken_swing=last_confirmed_high, at_datetime=last_dt, at_price=last_close,
            reason=f"{pair}: bullish CHoCH — price broke above the last lower high at {key_high:.5f}, "
                   f"first sign the downtrend may be reversing."
        )

    state.trend = trend
    state.key_high = key_high
    state.key_low = key_low
    state.last_event = event
    if event:
        state.history.append(event)
    return state


def is_structure_invalidated(state: StructureState, trade_direction: str) -> Optional[StructureEvent]:
    """
    Given an open trade's direction, return the StructureEvent that
    invalidates it (a CHoCH against the trade), or None if still valid.
    Used by trade_manager's monitoring loop.
    """
    if state.last_event is None:
        return None
    if state.last_event.kind == "CHoCH":
        if trade_direction == "long" and state.last_event.direction == "bearish":
            return state.last_event
        if trade_direction == "short" and state.last_event.direction == "bullish":
            return state.last_event
    return None

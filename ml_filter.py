"""
Aura FX - ML Confluence Filter (STUB)

This is intentionally a placeholder. See README "Leftover work" for why:
a real confluence scorer needs a labeled historical dataset of structure-
break setups (win/loss outcomes) before it can be trained, which this
scaffold doesn't have yet.

Once AURUM's feature engineering pipeline is adapted for swing timeframes
(D1/H4/H1 features instead of intraday), wire the trained model in here
and flip ML_FILTER_ENABLED = True in config.py.
"""
from config import ML_FILTER_ENABLED, ML_CONFLUENCE_THRESHOLD


def score_setup(features: dict) -> float:
    """
    Returns a confluence score 0-1. Currently a stub that always passes,
    so the bot runs on pure structure rules until a real model is trained.
    """
    if not ML_FILTER_ENABLED:
        return 1.0
    # TODO: load trained XGBoost model (adapted from AURUM's pipeline) and
    # score real feature vectors here.
    raise NotImplementedError("ML_FILTER_ENABLED is True but no model is wired in yet.")


def passes_filter(features: dict) -> bool:
    return score_setup(features) >= ML_CONFLUENCE_THRESHOLD

"""
Compute the factor scores that drive stock selection.

OWNER: Person A (data/strategy)

Recommended starting point (see docs/strategy_notes.md for the full rationale):
a price-only composite of momentum + low-volatility, since both are computable
cleanly from OHLCV alone and avoid the messiness of sourcing point-in-time
fundamentals for ~300 mid/smallcap names in a short timeline. Add a
value/quality leg later only if there's time and a clean data source for it.

TODO:
- momentum_score(prices, lookback_months=12, skip_months=1): classic 12-1
  momentum (cumulative return over the lookback, excluding the most recent
  month to avoid short-term reversal contamination).
- low_vol_score(prices, lookback_months=6): negative of realised daily-return
  volatility over the lookback (lower vol -> higher score).
- liquidity_filter(prices, volumes, min_avg_daily_turnover): drop illiquid
  names before ranking — an evaluator will notice if the strategy "selects"
  a stock that's barely tradeable.
- composite_score(...): z-score each factor cross-sectionally on each
  rebalance date, combine with fixed, documented weights (e.g. 0.5/0.5).
  Keep the combination rule constant across the whole backtest — no
  stock-by-stock tuning (this is explicitly flagged in the guidelines).
"""

import pandas as pd


def momentum_score(prices: pd.DataFrame, lookback_months: int = 12, skip_months: int = 1) -> pd.Series:
    raise NotImplementedError


def low_vol_score(prices: pd.DataFrame, lookback_months: int = 6) -> pd.Series:
    raise NotImplementedError


def composite_score(factor_frames: dict[str, pd.Series], weights: dict[str, float]) -> pd.Series:
    raise NotImplementedError

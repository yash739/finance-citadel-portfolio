"""
Compute the factor scores that drive stock selection.

OWNER: Person A (data/strategy)

A price-only composite of momentum + low-volatility. Both are computable cleanly from
OHLCV alone, which avoids sourcing point-in-time fundamentals for ~300 mid/smallcap
names on this timeline. Both are long-documented, non-overfit factors, which is the
honest answer to "why should this generalise out-of-sample?".

NO LOOK-AHEAD - THE CONTRACT FOR THIS MODULE
Every function here scores using the LAST rows of whatever `prices` frame it is
handed. It does not know the rebalance date. The caller (backtest.py) is responsible
for passing `prices.loc[:rebalance_date]` so that the final row is the rebalance date
itself. Passing the full panel would silently score on future data and invalidate the
entire backtest. This is the single most dangerous seam in the codebase.

The combination rule is fixed in config.yaml and constant across the whole backtest -
no per-stock overrides and no re-tuning between the in-sample and out-of-sample runs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# NSE trades ~21 days a month; used to convert month-denominated lookbacks to rows.
TRADING_DAYS_PER_MONTH = 21

# A factor is only computed for a stock with at least this fraction of its window
# populated - otherwise a freshly-listed name gets a score built on three days of data.
MIN_COVERAGE = 0.80


def _window(prices: pd.DataFrame, n_rows: int) -> pd.DataFrame:
    """Last `n_rows` rows of the frame (the caller has already truncated to as-of)."""
    return prices.iloc[-n_rows:] if n_rows < len(prices) else prices


def _enough_data(window: pd.DataFrame, required_rows: int) -> pd.Series:
    """Boolean mask of tickers with enough non-NaN observations in `window`."""
    return window.notna().sum() >= int(MIN_COVERAGE * required_rows)


def momentum_score(
    prices: pd.DataFrame, lookback_months: int = 12, skip_months: int = 1
) -> pd.Series:
    """Classic 12-1 momentum: cumulative return over the lookback, excluding the
    most recent `skip_months`.

    The skip is not cosmetic - the most recent month is contaminated by short-term
    reversal, so including it measurably degrades the factor.

    `prices` must end on the rebalance date (see module docstring).
    """
    lookback_rows = lookback_months * TRADING_DAYS_PER_MONTH
    skip_rows = skip_months * TRADING_DAYS_PER_MONTH

    # The skip must leave at least one row of formation period inside the lookback
    # window. If it does not (skip >= lookback), the factor is undefined rather than
    # a crash - guard it explicitly so a parameter sweep that crosses this boundary
    # returns NaN instead of an IndexError deep in the accounting loop.
    if lookback_rows <= 0 or skip_rows + 1 > lookback_rows:
        return pd.Series(np.nan, index=prices.columns, name="momentum")

    if len(prices) < lookback_rows:
        return pd.Series(np.nan, index=prices.columns, name="momentum")

    window = _window(prices, lookback_rows)
    start_px = window.iloc[0]
    # Price as of `skip_months` ago, i.e. the end of the formation period.
    end_px = window.iloc[-(skip_rows + 1)] if skip_rows > 0 else window.iloc[-1]

    score = (end_px / start_px) - 1.0
    score[~_enough_data(window, lookback_rows)] = np.nan
    score[(start_px <= 0) | start_px.isna() | end_px.isna()] = np.nan
    return score.rename("momentum")


def low_vol_score(prices: pd.DataFrame, lookback_months: int = 6) -> pd.Series:
    """Negative realised volatility of daily returns - lower vol scores higher.

    Returned annualised so the number is human-readable in the trade log/report,
    though only the cross-sectional ranking actually matters downstream.

    `prices` must end on the rebalance date (see module docstring).
    """
    lookback_rows = lookback_months * TRADING_DAYS_PER_MONTH
    window = _window(prices, lookback_rows + 1)

    rets = window.pct_change(fill_method=None).iloc[1:]
    vol = rets.std() * np.sqrt(252)

    score = -vol
    score[~_enough_data(window, lookback_rows)] = np.nan
    # A stock that literally never moved is stale data, not a low-risk stock.
    score[vol <= 0] = np.nan
    return score.rename("low_vol")


def average_turnover(
    prices: pd.DataFrame, volumes: pd.DataFrame, lookback_months: int = 3
) -> pd.Series:
    """Average daily rupee turnover (close x volume) over the lookback.

    Rupee turnover rather than share count, because 1000 shares of a Rs 50 stock and
    1000 shares of a Rs 5000 stock are not comparable liquidity.
    """
    lookback_rows = lookback_months * TRADING_DAYS_PER_MONTH
    px = _window(prices, lookback_rows)
    vol = volumes.reindex(index=px.index, columns=px.columns)
    return (px * vol).mean().rename("turnover")


def liquidity_filter(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    min_avg_daily_turnover: float,
    lookback_months: int = 3,
) -> pd.Index:
    """Tickers whose average daily turnover clears the threshold.

    Applied BEFORE ranking. An evaluator will notice if the strategy "selects" a name
    that could not absorb a Rs 10-25 lakh position without moving the price.
    """
    turnover = average_turnover(prices, volumes, lookback_months)
    return turnover.index[turnover >= min_avg_daily_turnover]


def zscore(s: pd.Series) -> pd.Series:
    """Cross-sectional z-score, computed only over names that actually have a value."""
    valid = s.dropna()
    if len(valid) < 2:
        return pd.Series(np.nan, index=s.index)
    sd = valid.std()
    if sd == 0 or not np.isfinite(sd):
        return pd.Series(np.nan, index=s.index)
    return (s - valid.mean()) / sd


def composite_score(
    factor_frames: dict[str, pd.Series], weights: dict[str, float]
) -> pd.Series:
    """Z-score each factor cross-sectionally, then combine with fixed weights.

    Z-scoring first is what makes the weights meaningful: raw momentum is a return
    (order 0.1-1.0) while raw low-vol is a negative volatility (order -0.2 to -0.8),
    so a naive weighted sum would be dominated by whichever factor happens to have
    the larger scale rather than by the weight we chose.

    Only stocks with a value for EVERY factor get a composite score. Partial scoring
    would quietly advantage names that are missing their weakest factor.
    """
    if not factor_frames:
        raise ValueError("composite_score called with no factors")

    missing = set(factor_frames) - set(weights)
    if missing:
        raise ValueError("no weight supplied for factor(s): %s" % sorted(missing))

    total_w = sum(weights[name] for name in factor_frames)
    if not np.isclose(total_w, 1.0):
        raise ValueError(
            "factor weights must sum to 1.0, got %.4f for %s"
            % (total_w, sorted(factor_frames))
        )

    z = pd.DataFrame({name: zscore(s) for name, s in factor_frames.items()})
    complete = z.notna().all(axis=1)

    w = pd.Series({name: weights[name] for name in z.columns})
    composite = (z * w).sum(axis=1)
    composite[~complete] = np.nan
    return composite.rename("composite")


def score_universe(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    config: dict,
) -> pd.Series:
    """Full scoring pipeline for one rebalance date.

    `prices`/`volumes` must be truncated to end on the rebalance date. Returns the
    composite score for every liquid, sufficiently-observed name; NaN elsewhere.
    """
    fcfg = config.get("factors", {})
    eligible = liquidity_filter(
        prices,
        volumes,
        min_avg_daily_turnover=fcfg.get("min_avg_daily_turnover_inr", 0.0),
        lookback_months=fcfg.get("liquidity_lookback_months", 3),
    )
    if len(eligible) == 0:
        return pd.Series(np.nan, index=prices.columns, name="composite")

    px = prices[eligible]
    weights = fcfg.get("weights", {"momentum": 0.5, "low_vol": 0.5})

    # Only compute the factors the caller actually asked for. This matters for the
    # single-factor experiments: if we always computed both, a momentum-only run
    # would still inherit low-vol's eligibility mask (composite_score drops any name
    # missing ANY factor), so it would not be a clean momentum-only test.
    builders = {
        "momentum": lambda: momentum_score(
            px,
            lookback_months=fcfg.get("momentum_lookback_months", 12),
            skip_months=fcfg.get("momentum_skip_months", 1),
        ),
        "low_vol": lambda: low_vol_score(
            px, lookback_months=fcfg.get("low_vol_lookback_months", 6)
        ),
    }
    unknown = set(weights) - set(builders)
    if unknown:
        raise ValueError(
            "unknown factor(s) in config.factors.weights: %s (known: %s)"
            % (sorted(unknown), sorted(builders))
        )

    factors = {name: builders[name]() for name in weights}
    scored = composite_score(factors, weights)
    return scored.reindex(prices.columns).rename("composite")

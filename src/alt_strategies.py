"""
Alternative signal families - strategies that are not just the composite retuned.

OWNER: shared

Run:  python -m src.alt_strategies            # head-to-head, per-year
      python -m src.alt_strategies --detail   # + full IS/OOS metrics table

Everything in src/experiments.py explores ONE idea: rank the universe cross-sectionally
on momentum and volatility, hold the top 10. Sweeping its parameters tells you where
that idea works best, not whether a different idea works better. This module holds the
harness fixed - same engine, same costs, same 10-name cap, same eligibility gate - and
swaps the signal itself.

Each scorer below has the same contract as factors.score_universe: it receives prices
and volumes TRUNCATED TO THE REBALANCE DATE and returns a score per ticker. Higher is
better. Names that fail the shared eligibility gate score NaN, so every family draws
from an identical pool and the comparison is like-for-like.

THE FAMILIES, AND WHY EACH IS WORTH A LOOK

  reversal          The direct opposite of momentum: buy the last month's biggest
                    losers. Short-horizon reversal is as well documented as momentum,
                    and it is the sharpest possible test of whether our momentum result
                    is real or an artifact of this sample.
  high_52w          Price relative to its 52-week high (George & Hwang). Correlated
                    with momentum but built differently - it anchors on a salient
                    reference price rather than a return over a window.
  residual_mom      Momentum after stripping out market beta. If plain momentum is
                    really just leveraged market exposure in disguise, this kills it.
  trend             Time-series rather than cross-sectional: how far above its own
                    200-day average a stock trades. Absolute, not relative, strength.
  acceleration      Change in momentum - recent 6m return minus the 6m before it. Picks
                    up names whose trend is improving rather than merely high.
  low_beta          Betting-against-beta. A cleaner version of the low-volatility leg,
                    since it isolates market sensitivity from idiosyncratic noise.
  consistency       Share of the last 12 months that were positive. A price-only proxy
                    for quality: steady compounding rather than one explosive quarter.
  illiquidity       Amihud: price impact per rupee traded. The illiquidity premium is
                    real but sits in direct tension with our tradeability screen, which
                    makes it a useful check on whether that screen costs us returns.

Two wrappers compose with any of the above:

  sector_neutral()  Rank within sector, so the book cannot become a bet on one industry.
  ensemble()        Average the cross-sectional z-scores of several families. Signals
                    that disagree often blend better than either alone.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.experiments import eligible_names
from src.factors import TRADING_DAYS_PER_MONTH as TPM
from src.factors import zscore

MONTH = TPM


def _gate(prices, volumes, config):
    """Shared eligibility pool - identical to what the main strategy may hold."""
    return eligible_names(prices, volumes, config)


def _blank(prices):
    return pd.Series(np.nan, index=prices.columns)


def _market(prices: pd.DataFrame) -> pd.Series:
    """Equal-weight return series of the tradeable panel - our market proxy.

    Built in-panel rather than from an index column, because the scorer only ever
    receives tradeable names. Uses only data up to the rebalance date.
    """
    return prices.pct_change(fill_method=None).mean(axis=1, skipna=True).fillna(0.0)


# ------------------------------------------------------------------ scorers


def reversal_scorer(lookback_months: int = 1):
    """Buy the biggest recent losers. Higher score = worse recent return."""
    def scorer(prices, volumes, config):
        pool = _gate(prices, volumes, config)
        if not len(pool):
            return _blank(prices)
        n = lookback_months * MONTH
        px = prices[pool]
        if len(px) < n + 1:
            return _blank(prices)
        ret = px.iloc[-1] / px.iloc[-(n + 1)] - 1.0
        return (-ret).reindex(prices.columns)
    return scorer


def high_52w_scorer():
    """Closeness to the trailing 52-week high, as a ratio in (0, 1]."""
    def scorer(prices, volumes, config):
        pool = _gate(prices, volumes, config)
        if not len(pool):
            return _blank(prices)
        px = prices[pool].iloc[-252:]
        if len(px) < 200:
            return _blank(prices)
        return (px.iloc[-1] / px.max()).reindex(prices.columns)
    return scorer


def residual_momentum_scorer(lookback_months: int = 12, skip_months: int = 2):
    """12-2 momentum with the market component regressed out.

    Beta is estimated over the same window against the equal-weight market proxy;
    the score is the stock's return minus beta times the market's return. What is
    left is the part of the move that was specific to the stock.
    """
    def scorer(prices, volumes, config):
        pool = _gate(prices, volumes, config)
        if not len(pool):
            return _blank(prices)
        n, skip = lookback_months * MONTH, skip_months * MONTH
        px = prices[pool]
        if len(px) < n + 1:
            return _blank(prices)

        window = px.iloc[-n:]
        end = -(skip + 1) if skip else -1
        rets = window.pct_change(fill_method=None).iloc[1:]
        mkt = _market(prices).reindex(rets.index).fillna(0.0)

        var = float(mkt.var(ddof=1))
        if not np.isfinite(var) or var <= 0:
            return _blank(prices)
        beta = rets.apply(lambda c: c.cov(mkt) / var)

        stock_ret = window.iloc[end] / window.iloc[0] - 1.0
        mkt_cum = float((1 + mkt.iloc[:len(mkt) + end + 1]).prod() - 1) if skip else float((1 + mkt).prod() - 1)
        resid = stock_ret - beta * mkt_cum
        return resid.reindex(prices.columns)
    return scorer


def trend_scorer(ma_days: int = 200):
    """Distance above the stock's own moving average. Absolute trend strength."""
    def scorer(prices, volumes, config):
        pool = _gate(prices, volumes, config)
        if not len(pool):
            return _blank(prices)
        px = prices[pool]
        if len(px) < ma_days:
            return _blank(prices)
        ma = px.iloc[-ma_days:].mean()
        return (px.iloc[-1] / ma - 1.0).reindex(prices.columns)
    return scorer


def acceleration_scorer(recent_months: int = 6, prior_months: int = 6):
    """Recent-window return minus the window before it: is the trend improving?"""
    def scorer(prices, volumes, config):
        pool = _gate(prices, volumes, config)
        if not len(pool):
            return _blank(prices)
        a, b = recent_months * MONTH, prior_months * MONTH
        px = prices[pool]
        if len(px) < a + b + 1:
            return _blank(prices)
        recent = px.iloc[-1] / px.iloc[-(a + 1)] - 1.0
        prior = px.iloc[-(a + 1)] / px.iloc[-(a + b + 1)] - 1.0
        return (recent - prior).reindex(prices.columns)
    return scorer


def low_beta_scorer(lookback_months: int = 12):
    """Betting-against-beta: lower market sensitivity scores higher."""
    def scorer(prices, volumes, config):
        pool = _gate(prices, volumes, config)
        if not len(pool):
            return _blank(prices)
        n = lookback_months * MONTH
        rets = prices[pool].iloc[-n:].pct_change(fill_method=None).iloc[1:]
        mkt = _market(prices).reindex(rets.index).fillna(0.0)
        var = float(mkt.var(ddof=1))
        if not np.isfinite(var) or var <= 0:
            return _blank(prices)
        beta = rets.apply(lambda c: c.cov(mkt) / var)
        return (-beta).reindex(prices.columns)
    return scorer


def consistency_scorer(lookback_months: int = 12):
    """Fraction of the last N months that were positive - steadiness, not size."""
    def scorer(prices, volumes, config):
        pool = _gate(prices, volumes, config)
        if not len(pool):
            return _blank(prices)
        n = lookback_months * MONTH
        px = prices[pool].iloc[-(n + 1):]
        if len(px) < n:
            return _blank(prices)
        marks = px.iloc[::MONTH]
        if len(marks) < 3:
            return _blank(prices)
        monthly = marks.pct_change(fill_method=None).iloc[1:]
        return (monthly > 0).mean().reindex(prices.columns)
    return scorer


def illiquidity_scorer(lookback_months: int = 3):
    """Amihud illiquidity: average |daily return| per rupee of turnover."""
    def scorer(prices, volumes, config):
        pool = _gate(prices, volumes, config)
        if not len(pool):
            return _blank(prices)
        n = lookback_months * MONTH
        px = prices[pool].iloc[-n:]
        vol = volumes[pool].reindex(index=px.index)
        turnover = (px * vol).replace(0.0, np.nan)
        impact = px.pct_change(fill_method=None).abs() / turnover
        return impact.mean().reindex(prices.columns)
    return scorer


# ----------------------------------------------------------------- wrappers


def sector_neutral(base_scorer, sector_map: dict):
    """Z-score the base signal WITHIN each sector.

    Stops the book becoming an accidental sector bet - plain momentum in this
    universe will happily load up on whichever industry ran hardest. Sectors with
    fewer than three scoreable names are dropped, since a z-score over two
    observations is meaningless.
    """
    def scorer(prices, volumes, config):
        raw = base_scorer(prices, volumes, config)
        sectors = pd.Series({t: sector_map.get(t, "?") for t in raw.index})
        out = pd.Series(np.nan, index=raw.index)
        for sec, idx in sectors.groupby(sectors).groups.items():
            sub = raw.reindex(idx).dropna()
            if len(sub) >= 3:
                out.loc[sub.index] = zscore(sub)
        return out
    return scorer


def ensemble(scorers: dict, weights: dict = None):
    """Average the cross-sectional z-scores of several signal families.

    A name must score on EVERY member to receive a blended score - partial blending
    would quietly favour whichever names are missing their weakest signal.
    """
    w = weights or {k: 1.0 / len(scorers) for k in scorers}
    total = sum(w[k] for k in scorers)
    if not np.isclose(total, 1.0):
        raise ValueError("ensemble weights must sum to 1.0, got %.4f" % total)

    def scorer(prices, volumes, config):
        zs = {}
        for name, fn in scorers.items():
            zs[name] = zscore(fn(prices, volumes, config))
        df = pd.DataFrame(zs)
        complete = df.notna().all(axis=1)
        blended = sum(df[k] * w[k] for k in df.columns)
        blended[~complete] = np.nan
        return blended
    return scorer


# ------------------------------------------------------------------ runner


def build_candidates(panels):
    """Every alternative family, plus the shipped strategy as the reference row."""
    sector_map = dict(zip(panels.universe["ticker"], panels.universe["sector"]))
    mom = None  # the shipped composite is score_fn=None (uses config)

    cands = {
        "SHIPPED mom55/lowvol45 skip2": (None, None),
        "-- single signal families --": (None, None),
        "reversal (1m loser)": (None, reversal_scorer(1)),
        "reversal (3m loser)": (None, reversal_scorer(3)),
        "52-week high proximity": (None, high_52w_scorer()),
        "residual momentum (beta-out)": (None, residual_momentum_scorer()),
        "trend (200d MA distance)": (None, trend_scorer(200)),
        "trend (100d MA distance)": (None, trend_scorer(100)),
        "acceleration (6m vs prior 6m)": (None, acceleration_scorer()),
        "low beta": (None, low_beta_scorer()),
        "return consistency": (None, consistency_scorer()),
        "illiquidity (Amihud)": (None, illiquidity_scorer()),
    }
    return cands, sector_map


def build_composites(panels, sector_map):
    """Sector-neutral and ensemble variants of whatever looked promising."""
    from src.factors import score_universe

    return {
        "-- wrappers and blends --": (None, None),
        "sector-neutral 52w high": (None, sector_neutral(high_52w_scorer(), sector_map)),
        "sector-neutral shipped": (None, sector_neutral(score_universe, sector_map)),
        "sector-neutral resid mom": (None, sector_neutral(residual_momentum_scorer(), sector_map)),
        "ens: shipped + 52w high": (None, ensemble(
            {"a": score_universe, "b": high_52w_scorer()}, {"a": .5, "b": .5})),
        "ens: shipped + trend": (None, ensemble(
            {"a": score_universe, "b": trend_scorer(200)}, {"a": .5, "b": .5})),
        "ens: shipped + resid mom": (None, ensemble(
            {"a": score_universe, "b": residual_momentum_scorer()}, {"a": .5, "b": .5})),
        "ens: shipped + consistency": (None, ensemble(
            {"a": score_universe, "b": consistency_scorer()}, {"a": .5, "b": .5})),
        "ens: 52w + trend + resid": (None, ensemble(
            {"a": high_52w_scorer(), "b": trend_scorer(200), "c": residual_momentum_scorer()},
            {"a": 1/3, "b": 1/3, "c": 1/3})),
    }


if __name__ == "__main__":
    import argparse

    from src.experiments import load_panels, print_header, print_row, run_strategy, yearly_robustness

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--detail", action="store_true", help="also print full IS/OOS metrics")
    args = parser.parse_args()

    panels = load_panels(args.config)
    singles, sector_map = build_candidates(panels)
    blends = build_composites(panels, sector_map)
    everything = {**singles, **blends}

    if args.detail:
        print_header("ALTERNATIVE SIGNAL FAMILIES - full metrics")
        for name, (ov, fn) in everything.items():
            if name.startswith("--"):
                print("-" * 100)
                continue
            print_row(name, run_strategy(panels, ov, fn))

    live = {k: v for k, v in everything.items() if not k.startswith("--")}
    yearly_robustness(panels, live)

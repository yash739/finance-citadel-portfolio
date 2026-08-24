"""
Factor tests.

The important ones are the look-ahead guards: momentum must ignore the skip window,
and every factor must be a function of the past only. A factor that quietly uses the
final row of the panel is the single easiest way to produce a beautiful, meaningless
backtest.
"""

import numpy as np
import pandas as pd
import pytest

from src.factors import (
    TRADING_DAYS_PER_MONTH,
    average_turnover,
    composite_score,
    liquidity_filter,
    low_vol_score,
    momentum_score,
    zscore,
)


def ramp(n=300, daily=0.001, start=100.0):
    """Deterministic compounding series - momentum is exactly computable on it."""
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.Series(start * (1 + daily) ** np.arange(n), index=idx)


# ---------------------------------------------------------------- momentum


def test_momentum_hand_computed_with_no_skip():
    """A 12-month (252-row) window on a series compounding at 0.1%/day.
    Return over the window = 1.001^251 - 1."""
    px = pd.DataFrame({"A": ramp(300)})
    score = momentum_score(px, lookback_months=12, skip_months=0)
    expected = (1.001 ** 251) - 1
    assert score["A"] == pytest.approx(expected, rel=1e-9)


def test_momentum_skip_excludes_the_recent_month():
    """With a 1-month skip the window still starts 252 rows back but ends 21 rows
    early, so the measured return covers 251 - 21 = 230 compounding steps."""
    px = pd.DataFrame({"A": ramp(300)})
    score = momentum_score(px, lookback_months=12, skip_months=1)
    expected = (1.001 ** (251 - TRADING_DAYS_PER_MONTH)) - 1
    assert score["A"] == pytest.approx(expected, rel=1e-9)


def test_momentum_ignores_a_spike_inside_the_skip_window():
    """THE look-ahead guard for momentum. Doubling the price in the final week must
    not change a 12-1 momentum score, because that week is inside the skipped month."""
    base = ramp(300)
    spiked = base.copy()
    spiked.iloc[-5:] = spiked.iloc[-5:] * 2.0

    a = momentum_score(pd.DataFrame({"A": base}), 12, 1)["A"]
    b = momentum_score(pd.DataFrame({"A": spiked}), 12, 1)["A"]
    assert a == pytest.approx(b), "the skip window is not actually being skipped"


def test_momentum_ranks_a_stronger_trend_higher():
    px = pd.DataFrame({"FAST": ramp(300, 0.002), "SLOW": ramp(300, 0.0005)})
    s = momentum_score(px, 12, 1)
    assert s["FAST"] > s["SLOW"]


def test_momentum_is_nan_without_enough_history():
    px = pd.DataFrame({"A": ramp(30)})
    assert np.isnan(momentum_score(px, lookback_months=12)["A"])


def test_momentum_is_nan_for_a_mostly_empty_column():
    """A name listed three days ago must not get a 12-month momentum score."""
    s = ramp(300)
    s.iloc[:-3] = np.nan
    assert np.isnan(momentum_score(pd.DataFrame({"A": s}), 12, 1)["A"])


# -------------------------------------------------------------- volatility


def test_low_vol_score_is_negative_volatility():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2020-01-01", periods=300)
    noisy = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 300))), index=idx)
    px = pd.DataFrame({"A": noisy})

    score = low_vol_score(px, lookback_months=6)
    rets = px.iloc[-(6 * TRADING_DAYS_PER_MONTH + 1):].pct_change().iloc[1:]
    expected = -(rets["A"].std() * np.sqrt(252))
    assert score["A"] == pytest.approx(expected)
    assert score["A"] < 0


def test_calmer_stock_scores_higher():
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2020-01-01", periods=300)
    calm = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.005, 300))), index=idx)
    wild = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.040, 300))), index=idx)
    s = low_vol_score(pd.DataFrame({"CALM": calm, "WILD": wild}), 6)
    assert s["CALM"] > s["WILD"]


def test_perfectly_flat_series_scores_nan_not_infinitely_good():
    """A stock that never moved is stale data, not a zero-risk asset. If this
    returned 0 it would rank first on the low-vol leg every single month."""
    px = pd.DataFrame({"FLAT": pd.Series(100.0, index=pd.bdate_range("2020-01-01", periods=300))})
    assert np.isnan(low_vol_score(px, 6)["FLAT"])


# --------------------------------------------------------------- liquidity


def test_average_turnover_is_price_times_volume():
    idx = pd.bdate_range("2020-01-01", periods=100)
    px = pd.DataFrame({"A": pd.Series(50.0, index=idx)})
    vol = pd.DataFrame({"A": pd.Series(1000.0, index=idx)})
    assert average_turnover(px, vol, 3)["A"] == pytest.approx(50_000.0)


def test_liquidity_filter_drops_thin_names():
    idx = pd.bdate_range("2020-01-01", periods=100)
    px = pd.DataFrame({"LIQUID": 100.0, "THIN": 100.0}, index=idx)
    vol = pd.DataFrame({"LIQUID": 1_000_000.0, "THIN": 10.0}, index=idx)
    eligible = liquidity_filter(px, vol, min_avg_daily_turnover=1_000_000, lookback_months=3)
    assert "LIQUID" in eligible
    assert "THIN" not in eligible


# --------------------------------------------------------------- composite


def test_zscore_hand_computed():
    """[1,2,3]: mean 2, sample std 1 -> [-1, 0, 1]."""
    z = zscore(pd.Series([1.0, 2.0, 3.0]))
    assert list(z.values) == pytest.approx([-1.0, 0.0, 1.0])


def test_zscore_of_constant_series_is_nan():
    assert zscore(pd.Series([5.0, 5.0, 5.0])).isna().all()


def test_composite_is_the_weighted_sum_of_zscores():
    """Equal weights on two identical factors reproduce the z-score itself."""
    f = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0})
    comp = composite_score({"mom": f, "vol": f}, {"mom": 0.5, "vol": 0.5})
    assert comp.values == pytest.approx(zscore(f).values)


def test_composite_puts_the_weight_where_you_asked():
    mom = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0})
    vol = pd.Series({"A": 3.0, "B": 2.0, "C": 1.0})
    comp = composite_score({"mom": mom, "vol": vol}, {"mom": 1.0, "vol": 0.0})
    assert comp["C"] > comp["A"], "a zero-weighted factor still moved the ranking"


def test_composite_requires_every_factor_present():
    """Partial scoring would advantage a name that is missing its weakest factor."""
    mom = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0})
    vol = pd.Series({"A": 1.0, "B": np.nan, "C": 3.0})
    comp = composite_score({"mom": mom, "vol": vol}, {"mom": 0.5, "vol": 0.5})
    assert np.isnan(comp["B"])
    assert comp[["A", "C"]].notna().all()


def test_composite_rejects_weights_that_do_not_sum_to_one():
    f = pd.Series({"A": 1.0, "B": 2.0})
    with pytest.raises(ValueError, match="sum to 1.0"):
        composite_score({"mom": f, "vol": f}, {"mom": 0.5, "vol": 0.9})


def test_composite_rejects_a_factor_with_no_weight():
    f = pd.Series({"A": 1.0, "B": 2.0})
    with pytest.raises(ValueError, match="no weight supplied"):
        composite_score({"mom": f, "vol": f}, {"mom": 1.0})


def test_composite_with_no_factors_raises():
    with pytest.raises(ValueError):
        composite_score({}, {})

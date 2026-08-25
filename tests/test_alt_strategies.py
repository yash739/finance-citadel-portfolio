"""
Tests for the alternative signal families.

These scorers only ever informed a *negative* result - none of them replaced the
shipped strategy - but a bug in one would have produced a fake negative just as
easily as a fake positive. Each is checked against a construction where the right
answer is known by inspection.
"""

import numpy as np
import pandas as pd
import pytest

from src.alt_strategies import (
    acceleration_scorer,
    consistency_scorer,
    ensemble,
    high_52w_scorer,
    illiquidity_scorer,
    low_beta_scorer,
    residual_momentum_scorer,
    reversal_scorer,
    sector_neutral,
    trend_scorer,
)
from tests.conftest import make_config, make_prices, make_volumes

CFG = make_config(factors={"min_avg_daily_turnover_inr": 0.0})


def panel(**series):
    idx = pd.bdate_range("2020-01-01", periods=400)
    return pd.DataFrame({k: v(len(idx)) for k, v in series.items()}, index=idx)


def rising(n, rate=0.001, start=100.0):
    return start * (1 + rate) ** np.arange(n)


def falling(n, rate=0.001, start=100.0):
    return start * (1 - rate) ** np.arange(n)


def noisy(n, sd=0.02, seed=0, drift=0.0):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(drift, sd, n)))


# ------------------------------------------------------------------ direction


def test_reversal_prefers_the_loser():
    """The whole point of reversal: the falling stock must score higher."""
    px = panel(UP=rising, DOWN=falling)
    s = reversal_scorer(1)(px, make_volumes(px), CFG)
    assert s["DOWN"] > s["UP"]


def test_reversal_is_the_negative_of_recent_return():
    px = panel(A=lambda n: rising(n, 0.002), B=lambda n: rising(n, 0.0005))
    s = reversal_scorer(1)(px, make_volumes(px), CFG)
    assert s["B"] > s["A"], "the weaker riser should score higher under reversal"


def test_trend_prefers_the_stock_above_its_average():
    px = panel(UP=rising, DOWN=falling)
    s = trend_scorer(200)(px, make_volumes(px), CFG)
    assert s["UP"] > 0 > s["DOWN"]


def test_52w_high_is_bounded_and_maxes_at_a_new_high():
    """A monotonically rising series sits exactly at its 52-week high -> 1.0."""
    px = panel(UP=rising, DOWN=falling)
    s = high_52w_scorer()(px, make_volumes(px), CFG)
    assert s["UP"] == pytest.approx(1.0)
    assert 0 < s["DOWN"] < 1.0


def test_acceleration_prefers_an_improving_trend():
    """FLAT_THEN_UP was flat then rallied; UP_THEN_FLAT did the reverse."""
    n = 400
    half = n // 2
    a = np.concatenate([np.full(half, 100.0), 100 * (1.003 ** np.arange(n - half))])
    b = np.concatenate([100 * (1.003 ** np.arange(half)),
                        np.full(n - half, 100 * 1.003 ** (half - 1))])
    idx = pd.bdate_range("2020-01-01", periods=n)
    px = pd.DataFrame({"FLAT_THEN_UP": a, "UP_THEN_FLAT": b}, index=idx)
    s = acceleration_scorer(6, 6)(px, make_volumes(px), CFG)
    assert s["FLAT_THEN_UP"] > s["UP_THEN_FLAT"]


def test_consistency_prefers_the_steady_compounder():
    px = panel(STEADY=lambda n: rising(n, 0.0008),
               CHOPPY=lambda n: noisy(n, 0.03, seed=5))
    s = consistency_scorer(12)(px, make_volumes(px), CFG)
    assert s["STEADY"] == pytest.approx(1.0)
    assert s["CHOPPY"] < 1.0


def test_low_beta_prefers_the_less_market_sensitive_name():
    """HIGH is built as 2x the market's daily move, LOW as 0.25x."""
    rng = np.random.default_rng(3)
    n = 400
    mkt = rng.normal(0.0004, 0.01, n)
    idx = pd.bdate_range("2020-01-01", periods=n)
    px = pd.DataFrame({
        "HIGH": 100 * np.exp(np.cumsum(2.0 * mkt)),
        "LOW": 100 * np.exp(np.cumsum(0.25 * mkt)),
        "MID": 100 * np.exp(np.cumsum(1.0 * mkt)),
    }, index=idx)
    s = low_beta_scorer(12)(px, make_volumes(px), CFG)
    assert s["LOW"] > s["MID"] > s["HIGH"]


def test_residual_momentum_discounts_pure_market_exposure():
    """LEVERED is just 2x the market; IDIO has the same total return but earns it
    independently. Residual momentum must prefer IDIO."""
    rng = np.random.default_rng(11)
    n = 400
    mkt = rng.normal(0.0008, 0.01, n)
    idio = rng.normal(0.0016, 0.01, n)
    idx = pd.bdate_range("2020-01-01", periods=n)
    px = pd.DataFrame({
        "LEVERED": 100 * np.exp(np.cumsum(2.0 * mkt)),
        "IDIO": 100 * np.exp(np.cumsum(idio)),
        "MKT_A": 100 * np.exp(np.cumsum(mkt)),
        "MKT_B": 100 * np.exp(np.cumsum(mkt + rng.normal(0, 0.001, n))),
    }, index=idx)
    s = residual_momentum_scorer(12, 2)(px, make_volumes(px), CFG)
    assert s.notna().sum() >= 3
    assert s["IDIO"] > s["LEVERED"]


def test_illiquidity_prefers_the_thinly_traded_name():
    px = panel(THIN=lambda n: noisy(n, 0.02, seed=1),
               THICK=lambda n: noisy(n, 0.02, seed=1))
    vol = make_volumes(px)
    vol["THIN"] = 1_000.0
    vol["THICK"] = 50_000_000.0
    s = illiquidity_scorer(3)(px, vol, CFG)
    assert s["THIN"] > s["THICK"]


# ------------------------------------------------------------- eligibility


def test_scorers_respect_the_liquidity_gate():
    """Every family must draw from the same pool, or the comparison is not like-for-like."""
    px = make_prices(400)
    vol = make_volumes(px, per_day=5_000_000)
    vol.loc[:, "CCC.NS"] = 1.0
    cfg = make_config(factors={"min_avg_daily_turnover_inr": 1_000_000_000})
    for fn in (reversal_scorer(1), high_52w_scorer(), trend_scorer(200),
               acceleration_scorer(), low_beta_scorer(), consistency_scorer()):
        s = fn(px, vol, cfg)
        assert np.isnan(s["CCC.NS"]), "%s let an illiquid name through" % fn


def test_scorers_return_nan_without_enough_history():
    px = make_prices(30)
    vol = make_volumes(px)
    for fn in (high_52w_scorer(), trend_scorer(200), acceleration_scorer()):
        assert fn(px, vol, CFG).isna().all()


# ---------------------------------------------------------------- wrappers


def test_ensemble_rejects_weights_that_do_not_sum_to_one():
    with pytest.raises(ValueError, match="sum to 1.0"):
        ensemble({"a": trend_scorer(), "b": high_52w_scorer()}, {"a": 0.5, "b": 0.9})


def test_ensemble_requires_every_member_to_score():
    """Partial blending would favour names missing their weakest signal."""
    px = make_prices(400)
    vol = make_volumes(px)

    def half_blind(p, v, c):
        s = trend_scorer(200)(p, v, c)
        s["AAA.NS"] = np.nan
        return s

    blend = ensemble({"a": trend_scorer(200), "b": half_blind}, {"a": 0.5, "b": 0.5})
    assert np.isnan(blend(px, vol, CFG)["AAA.NS"])


def test_ensemble_of_one_signal_with_itself_preserves_ranking():
    px = make_prices(400)
    vol = make_volumes(px)
    base = trend_scorer(200)
    blend = ensemble({"a": base, "b": base}, {"a": 0.5, "b": 0.5})
    raw, mixed = base(px, vol, CFG).dropna(), blend(px, vol, CFG).dropna()
    common = raw.index.intersection(mixed.index)
    assert list(raw[common].rank()) == list(mixed[common].rank())


def test_sector_neutral_drops_sectors_with_too_few_names():
    """A z-score over two observations is meaningless, so those names score NaN."""
    px = make_prices(400)
    vol = make_volumes(px)
    smap = {"AAA.NS": "Big", "BBB.NS": "Big", "CCC.NS": "Big", "DDD.NS": "Lonely"}
    s = sector_neutral(trend_scorer(200), smap)(px, vol, CFG)
    assert np.isnan(s["DDD.NS"]), "a one-name sector should not produce a score"
    assert s[["AAA.NS", "BBB.NS", "CCC.NS"]].notna().all()


def test_sector_neutral_ranks_within_not_across_sectors():
    """Two sectors with very different raw levels must both centre on zero."""
    idx = pd.bdate_range("2020-01-01", periods=400)
    px = pd.DataFrame({
        "H1": rising(400, 0.003), "H2": rising(400, 0.0028), "H3": rising(400, 0.0026),
        "L1": rising(400, 0.0003), "L2": rising(400, 0.0002), "L3": rising(400, 0.0001),
    }, index=idx)
    smap = {t: ("HOT" if t.startswith("H") else "COLD") for t in px.columns}
    s = sector_neutral(trend_scorer(200), smap)(px, make_volumes(px), CFG)
    assert s[["H1", "H2", "H3"]].mean() == pytest.approx(0.0, abs=1e-9)
    assert s[["L1", "L2", "L3"]].mean() == pytest.approx(0.0, abs=1e-9)
    # and the best name in the cold sector beats the worst in the hot one
    assert s["L1"] > s["H3"]

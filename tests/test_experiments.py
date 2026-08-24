"""
Tests for the experiment harness and the engine hooks it depends on.

The harness is what the strategy choice was made from, so a bug here would have
silently produced the wrong final strategy. One already did: `deep_merge` originally
merged the `weights` dict, turning a momentum-only override into a 1.5-weight
composite. test_weights_replace_not_merge exists so that cannot come back.
"""

import numpy as np
import pandas as pd
import pytest

from src.backtest import get_rebalance_dates, run_backtest
from src.experiments import (
    deep_merge,
    eligible_names,
    make_alphabetical_scorer,
    make_random_scorer,
    make_regime_filtered_scorer,
)
from tests.conftest import make_config, make_prices, make_universe, make_volumes


# ------------------------------------------------------------- deep_merge


def test_weights_replace_not_merge():
    """THE regression test. Merging weights produced {momentum:1.0, low_vol:0.5},
    which sums to 1.5 and is not a momentum-only strategy."""
    base = {"factors": {"weights": {"momentum": 0.5, "low_vol": 0.5}}}
    out = deep_merge(base, {"factors": {"weights": {"momentum": 1.0}}})
    assert out["factors"]["weights"] == {"momentum": 1.0}
    assert sum(out["factors"]["weights"].values()) == pytest.approx(1.0)


def test_other_nested_dicts_still_merge():
    base = {"factors": {"momentum_lookback_months": 12, "low_vol_lookback_months": 6}}
    out = deep_merge(base, {"factors": {"momentum_lookback_months": 9}})
    assert out["factors"]["momentum_lookback_months"] == 9
    assert out["factors"]["low_vol_lookback_months"] == 6


def test_deep_merge_does_not_mutate_the_base():
    base = {"factors": {"weights": {"momentum": 0.5}}}
    deep_merge(base, {"factors": {"weights": {"momentum": 1.0}}})
    assert base["factors"]["weights"] == {"momentum": 0.5}


# ---------------------------------------------------------------- scorers


def test_random_scorer_is_deterministic():
    """Same seed, same date -> same scores, or none of the experiments reproduce."""
    px = make_prices(300)
    vol = make_volumes(px)
    cfg = make_config()
    a = make_random_scorer(3)(px, vol, cfg)
    b = make_random_scorer(3)(px, vol, cfg)
    pd.testing.assert_series_equal(a, b)


def test_different_seeds_give_different_scores():
    px, cfg = make_prices(300), make_config()
    vol = make_volumes(px)
    a = make_random_scorer(1)(px, vol, cfg)
    b = make_random_scorer(2)(px, vol, cfg)
    assert not a.equals(b)


def test_random_scorer_only_scores_eligible_names():
    """A random baseline that could hold unlisted names would not be a fair control."""
    px = make_prices(300)
    px.loc[:, "DDD.NS"] = np.nan  # never listed
    vol = make_volumes(px)
    scores = make_random_scorer(0)(px, vol, make_config())
    assert np.isnan(scores["DDD.NS"])


def test_alphabetical_scorer_prefers_earlier_names():
    px, cfg = make_prices(300), make_config()
    scores = make_alphabetical_scorer()(px, make_volumes(px), cfg)
    assert scores["AAA.NS"] > scores["BBB.NS"] > scores["CCC.NS"]


def test_eligible_names_excludes_illiquid():
    px = make_prices(300)
    vol = make_volumes(px, per_day=1_000_000)
    vol.loc[:, "CCC.NS"] = 1.0
    cfg = make_config(factors={"min_avg_daily_turnover_inr": 1_000_000})
    assert "CCC.NS" not in eligible_names(px, vol, cfg)
    assert "AAA.NS" in eligible_names(px, vol, cfg)


# ----------------------------------------------------------- regime filter


def test_regime_scorer_flags_risk_off_in_a_downtrend():
    idx = pd.bdate_range("2020-01-01", periods=300)
    falling = pd.DataFrame(
        {t: 100 * np.exp(np.cumsum(np.full(300, -0.002))) for t in ["AAA.NS", "BBB.NS"]},
        index=idx,
    )
    vol = make_volumes(falling)
    scores = make_regime_filtered_scorer(200)(falling, vol, make_config())
    assert scores.attrs.get("risk_off") is True


def test_regime_scorer_stays_invested_in_an_uptrend():
    idx = pd.bdate_range("2020-01-01", periods=300)
    rising = pd.DataFrame(
        {t: 100 * np.exp(np.cumsum(np.full(300, 0.002))) for t in ["AAA.NS", "BBB.NS"]},
        index=idx,
    )
    scores = make_regime_filtered_scorer(200)(rising, make_volumes(rising), make_config())
    assert not scores.attrs.get("risk_off")


def test_risk_off_liquidates_the_book():
    """An explicit risk-off signal must sell down to cash - which is different from
    'no opinion', where the book should be left alone."""
    prices = make_prices(400)
    volumes = make_volumes(prices)
    window = prices.loc["2021-01-01":]

    def always_risk_off(px, vol, cfg):
        s = pd.Series(1.0, index=px.columns)
        s.attrs["risk_off"] = True
        return s

    result = run_backtest(
        window, make_universe(), make_config(),
        volumes=volumes.loc["2021-01-01":], history=prices.loc[:"2020-12-31"],
        volume_history=volumes.loc[:"2020-12-31"], score_fn=always_risk_off,
    )
    assert len(result["open_positions"]) == 0, "risk-off did not liquidate"
    assert result["nav"].iloc[-1] == pytest.approx(result["cash"].iloc[-1])


# ------------------------------------------------------ buy-and-hold frequency


def test_once_frequency_rebalances_exactly_once():
    idx = pd.bdate_range("2021-01-01", periods=300)
    assert get_rebalance_dates(idx, "ONCE") == [idx[0]]


def test_buy_and_hold_has_no_sells_after_the_first_fill():
    prices = make_prices(400)
    volumes = make_volumes(prices)
    cfg = make_config(rebalance={"frequency": "ONCE"})
    result = run_backtest(
        prices.loc["2021-01-01":], make_universe(), cfg,
        volumes=volumes.loc["2021-01-01":], history=prices.loc[:"2020-12-31"],
        volume_history=volumes.loc[:"2020-12-31"],
    )
    assert (result["trades"]["side"] == "BUY").all(), "buy-and-hold sold something"
    assert result["trades"]["date"].nunique() == 1, "traded on more than one day"


# ------------------------------------------------ pluggable scorer contract


def test_score_fn_overrides_the_default_scorer():
    """A scorer pinning one name must produce a book containing it."""
    prices = make_prices(400)
    volumes = make_volumes(prices)

    def only_bbb(px, vol, cfg):
        s = pd.Series(np.nan, index=px.columns)
        s["BBB.NS"] = 1.0
        return s

    result = run_backtest(
        prices.loc["2021-01-01":], make_universe(),
        make_config(universe={"max_holdings": 1}, rebalance={"max_weight_per_stock": 1.0}),
        volumes=volumes.loc["2021-01-01":], history=prices.loc[:"2020-12-31"],
        volume_history=volumes.loc[:"2020-12-31"], score_fn=only_bbb,
    )
    assert set(result["trades"]["ticker"]) == {"BBB.NS"}


def test_default_scorer_used_when_score_fn_is_none():
    prices = make_prices(400)
    volumes = make_volumes(prices)
    result = run_backtest(
        prices.loc["2021-01-01":], make_universe(), make_config(),
        volumes=volumes.loc["2021-01-01":], history=prices.loc[:"2020-12-31"],
        volume_history=volumes.loc[:"2020-12-31"], score_fn=None,
    )
    assert len(result["trades"]) > 0

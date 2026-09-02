"""
Tests for the bias decomposition.

The decomposition is the number that keeps the report honest, so it needs to be right
in the direction that matters: it must not quietly credit the strategy for return that
came from the universe.
"""

import numpy as np
import pandas as pd
import pytest

from src.diagnostics import decompose, equal_weight_universe
from src.metrics import annualised_return
from tests.conftest import make_prices


def nav(values, start="2021-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


# ------------------------------------------------- equal_weight_universe


def test_equal_weight_of_one_stock_tracks_that_stock():
    idx = pd.bdate_range("2021-01-01", periods=5)
    px = pd.DataFrame({"A": [100.0, 110.0, 121.0, 133.1, 146.41]}, index=idx)
    ew = equal_weight_universe(px, ["A"], 1_000_000)
    # 10% a day compounding from Rs 10 lakh.
    assert ew.iloc[-1] == pytest.approx(1_000_000 * 1.1 ** 4)


def test_equal_weight_averages_two_stocks():
    """One stock +10%/day, one flat -> portfolio earns 5%/day."""
    idx = pd.bdate_range("2021-01-01", periods=3)
    px = pd.DataFrame({"UP": [100.0, 110.0, 121.0], "FLAT": [50.0, 50.0, 50.0]}, index=idx)
    ew = equal_weight_universe(px, ["UP", "FLAT"], 1_000_000)
    assert ew.iloc[-1] == pytest.approx(1_000_000 * 1.05 ** 2)


def test_unlisted_names_are_excluded_not_treated_as_zero_return():
    """A stock that lists mid-window must not drag the average before it existed.

    Days 1-2 only LATE is absent, so the portfolio is 100% EARLY and earns EARLY's
    10%. If the NaN were coerced to a 0% return, the portfolio would earn only 5%.
    """
    idx = pd.bdate_range("2021-01-01", periods=3)
    px = pd.DataFrame(
        {"EARLY": [100.0, 110.0, 121.0], "LATE": [np.nan, np.nan, 200.0]}, index=idx
    )
    ew = equal_weight_universe(px, ["EARLY", "LATE"], 1_000_000)
    assert ew.iloc[1] == pytest.approx(1_100_000.0)


def test_missing_tickers_are_skipped_not_fatal():
    px = make_prices(50)
    ew = equal_weight_universe(px, ["AAA.NS", "NOT_A_REAL_TICKER.NS"], 1_000_000)
    assert len(ew) == len(px)
    assert ew.notna().all()


def test_all_tickers_missing_raises():
    with pytest.raises(KeyError):
        equal_weight_universe(make_prices(20), ["NOPE.NS"], 1_000_000)


def test_starts_at_starting_capital():
    ew = equal_weight_universe(make_prices(30), ["AAA.NS", "BBB.NS"], 1_000_000)
    assert ew.iloc[0] == pytest.approx(1_000_000.0)


# ---------------------------------------------------------- decompose


def test_decomposition_components_sum_to_total_excess():
    """composition + selection must equal the total excess, exactly - otherwise the
    attribution is hiding return somewhere."""
    strat = nav([100, 130])
    uni = nav([100, 115])
    index = nav([100, 105])
    d = decompose(strat, uni, index)
    assert (
        d["attributable_to_universe_composition"] + d["attributable_to_strategy_selection"]
        == pytest.approx(d["total_excess_over_index"])
    )


def test_composition_is_universe_minus_index():
    strat, uni, index = nav([100, 130]), nav([100, 115]), nav([100, 105])
    d = decompose(strat, uni, index)
    assert d["attributable_to_universe_composition"] == pytest.approx(
        annualised_return(uni) - annualised_return(index)
    )


def test_flags_when_strategy_loses_to_its_own_universe():
    """The out-of-sample case we actually hit: the universe outperforms the strategy."""
    strat = nav([100, 101])
    uni = nav([100, 110])
    index = nav([100, 95])
    d = decompose(strat, uni, index)
    assert d["strategy_beats_own_universe"] is False
    assert d["attributable_to_strategy_selection"] < 0


def test_flags_when_strategy_genuinely_adds_value():
    d = decompose(nav([100, 140]), nav([100, 110]), nav([100, 105]))
    assert d["strategy_beats_own_universe"] is True
    assert d["attributable_to_strategy_selection"] > 0


def test_zero_composition_when_universe_matches_index():
    d = decompose(nav([100, 130]), nav([100, 110]), nav([100, 110]))
    assert d["attributable_to_universe_composition"] == pytest.approx(0.0)
    assert d["composition_share_of_excess"] == pytest.approx(0.0)

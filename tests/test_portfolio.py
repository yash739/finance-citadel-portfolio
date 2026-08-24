"""
Selection and weighting tests - all hand-computed.

The weight-capping arithmetic is written out in each docstring, because a redistribute
-until-stable loop is exactly the kind of code that looks right and is off by a few
basis points.
"""

import numpy as np
import pandas as pd
import pytest

from src.portfolio import select_stocks, weight_stocks


def scores(**kwargs):
    return pd.Series(kwargs, dtype=float)


# ---------------------------------------------------------------- selection


def test_selects_top_n_by_score():
    s = scores(A=3.0, B=1.0, C=2.0, D=-1.0)
    assert select_stocks(s, max_holdings=2) == ["A", "C"]


def test_never_returns_more_than_max_holdings():
    s = pd.Series({("T%d" % i): float(i) for i in range(50)})
    assert len(select_stocks(s, max_holdings=10)) == 10


def test_nan_scores_are_never_selected():
    s = scores(A=3.0, B=np.nan, C=1.0)
    assert "B" not in select_stocks(s, max_holdings=3)


def test_empty_scores_gives_empty_book():
    assert select_stocks(pd.Series(dtype=float), max_holdings=10) == []
    assert select_stocks(scores(A=np.nan), max_holdings=10) == []


def test_hysteresis_keeps_a_held_name_that_slipped():
    """C is held and sits at rank 3. With max_holdings=2 it would normally be sold,
    but buffer_rank=3 keeps it, and it displaces the would-be new entrant B."""
    s = scores(A=5.0, B=4.0, C=3.0, D=2.0)
    held = select_stocks(s, max_holdings=2, current_holdings={"C"}, buffer_rank=3)
    assert "C" in held
    assert len(held) == 2


def test_hysteresis_drops_a_name_that_fell_past_the_buffer():
    """D is held but sits at rank 4, outside buffer_rank=3, so it goes."""
    s = scores(A=5.0, B=4.0, C=3.0, D=2.0)
    held = select_stocks(s, max_holdings=2, current_holdings={"D"}, buffer_rank=3)
    assert "D" not in held
    assert held == ["A", "B"]


def test_without_hysteresis_the_ranking_wins():
    s = scores(A=5.0, B=4.0, C=3.0)
    assert select_stocks(s, max_holdings=2, current_holdings={"C"}, buffer_rank=None) == ["A", "B"]


# ---------------------------------------------------------------- weighting


def test_equal_weight_hand_computed():
    """Four names, cap 0.6, no cap binds: 1/4 = 0.25 each."""
    w = weight_stocks(["A", "B", "C", "D"], scores(A=1, B=2, C=3, D=4),
                      scheme="equal_weight", max_weight_per_stock=0.6)
    assert np.allclose(w.values, 0.25)
    assert w.sum() == pytest.approx(1.0)


def test_score_proportional_uses_ranks_hand_computed():
    """Two names, ranks 1 and 2 -> raw [1,2] -> [1/3, 2/3].
    Cap 0.6 binds on the second: excess = 2/3 - 0.6 = 0.0667 moves to the first,
    which has headroom 0.6 - 0.3333 = 0.2667 and absorbs all of it.
    Result: A = 0.4, B = 0.6."""
    w = weight_stocks(["A", "B"], scores(A=1.0, B=2.0),
                      scheme="score_proportional", max_weight_per_stock=0.6)
    assert w["A"] == pytest.approx(0.4)
    assert w["B"] == pytest.approx(0.6)
    assert w.sum() == pytest.approx(1.0)


def test_score_proportional_is_monotone_in_score():
    w = weight_stocks(["A", "B", "C"], scores(A=-2.0, B=0.0, C=5.0),
                      scheme="score_proportional", max_weight_per_stock=1.0)
    assert w["A"] < w["B"] < w["C"]


def test_negative_scores_never_produce_negative_weights():
    """Long-only mandate: a book of all-negative z-scores must still be long-only."""
    w = weight_stocks(["A", "B", "C"], scores(A=-3.0, B=-2.0, C=-1.0),
                      scheme="score_proportional", max_weight_per_stock=0.5)
    assert (w >= 0).all(), "a negative composite score leaked into a short position"


def test_cap_is_never_breached_across_many_shapes():
    for n in (2, 3, 5, 10):
        for cap in (0.15, 0.25, 0.4, 1.0):
            names = ["T%d" % i for i in range(n)]
            s = pd.Series({name: float(i) for i, name in enumerate(names)})
            w = weight_stocks(names, s, scheme="score_proportional",
                              max_weight_per_stock=cap)
            assert w.max() <= cap + 1e-9, "n=%d cap=%.2f breached" % (n, cap)


def test_underinvested_when_cap_makes_full_investment_impossible():
    """Three names capped at 25% each cannot absorb 100% of capital.
    Weights must sum to 0.75 and the remaining 25% is held as cash - the engine
    must not quietly breach the risk limit to stay fully invested."""
    w = weight_stocks(["A", "B", "C"], scores(A=1, B=2, C=3),
                      scheme="score_proportional", max_weight_per_stock=0.25)
    assert np.allclose(w.values, 0.25)
    assert w.sum() == pytest.approx(0.75)


def test_inverse_vol_favours_the_calmer_stock():
    """Vols 0.10 and 0.40 -> raw 10 and 2.5 -> 0.8 / 0.2."""
    w = weight_stocks(["A", "B"], scores(A=1.0, B=1.0), scheme="inverse_vol",
                      max_weight_per_stock=1.0,
                      volatilities=pd.Series({"A": 0.10, "B": 0.40}))
    assert w["A"] == pytest.approx(0.8)
    assert w["B"] == pytest.approx(0.2)


def test_inverse_vol_without_volatilities_raises():
    with pytest.raises(ValueError):
        weight_stocks(["A"], scores(A=1.0), scheme="inverse_vol")


def test_unknown_scheme_raises():
    with pytest.raises(ValueError, match="unknown weighting_scheme"):
        weight_stocks(["A"], scores(A=1.0), scheme="martingale")


def test_empty_selection_gives_empty_weights():
    assert weight_stocks([], scores(A=1.0)).empty

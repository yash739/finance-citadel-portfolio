"""
Metric tests, every one against a hand-computed value.

Where a number is checked, the arithmetic is written out in the docstring so a
reviewer can verify it without running anything. These are the numbers that go into
the report, so "it looked about right" is not good enough.
"""

import numpy as np
import pandas as pd
import pytest

from src.metrics import (
    accuracy,
    annualised_return,
    annualised_volatility,
    calmar_ratio,
    gain_to_loss_ratio,
    max_drawdown,
    max_drawdown_detail,
    profit_factor,
    sharpe_ratio,
    total_net_pnl,
    total_return,
    trade_stats,
)


def nav_series(values, start="2021-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


# ------------------------------------------------------------------ returns


def test_total_return_hand_computed():
    """100 -> 110 -> 99.  99/100 - 1 = -0.01."""
    assert total_return(nav_series([100, 110, 99])) == pytest.approx(-0.01)


def test_total_net_pnl_uses_starting_capital():
    """Final NAV 1,050,000 against Rs 10 lakh capital = Rs 50,000 profit."""
    nav = nav_series([1_000_000, 1_020_000, 1_050_000])
    assert total_net_pnl(nav, 1_000_000) == pytest.approx(50_000.0)


def test_total_net_pnl_defaults_to_first_nav():
    nav = nav_series([1_000_000, 1_050_000])
    assert total_net_pnl(nav) == pytest.approx(50_000.0)


def test_annualised_return_hand_computed():
    """100 -> 121 over 2 trading days: 1.21^(252/2) - 1."""
    nav = nav_series([100, 110, 121])
    expected = 1.21 ** (252 / 2) - 1
    assert annualised_return(nav) == pytest.approx(expected)


def test_annualised_return_of_flat_series_is_zero():
    assert annualised_return(nav_series([100] * 10)) == pytest.approx(0.0)


def test_annualised_volatility_hand_computed():
    """Daily returns +10%, -10%.  Sample std (ddof=1) = sqrt(0.02) = 0.1414214.
    Annualised = 0.1414214 * sqrt(252)."""
    nav = nav_series([100, 110, 99])
    expected = np.sqrt(0.02) * np.sqrt(252)
    assert annualised_volatility(nav) == pytest.approx(expected)


# ---------------------------------------------------------------- drawdown


def test_max_drawdown_hand_computed():
    """Peak 110, trough 99.  99/110 - 1 = -0.1 exactly."""
    assert max_drawdown(nav_series([100, 110, 99])) == pytest.approx(-0.10)


def test_max_drawdown_is_zero_for_monotonic_series():
    assert max_drawdown(nav_series([100, 101, 102, 103])) == pytest.approx(0.0)


def test_max_drawdown_takes_the_deepest_not_the_latest():
    """Two declines: 100->50 (-50%) then 80->72 (-10%). Must report -50%."""
    assert max_drawdown(nav_series([100, 50, 80, 72])) == pytest.approx(-0.50)


def test_max_drawdown_detail_finds_peak_and_trough():
    nav = nav_series([100, 120, 90, 130])
    d = max_drawdown_detail(nav)
    assert d["max_drawdown"] == pytest.approx(90 / 120 - 1)
    assert d["peak_date"] == str(nav.index[1])
    assert d["trough_date"] == str(nav.index[2])
    assert d["recovered"] is True


def test_max_drawdown_detail_reports_unrecovered():
    d = max_drawdown_detail(nav_series([100, 120, 90, 95]))
    assert d["recovered"] is False
    assert d["recovery_date"] is None


# ------------------------------------------------------------------ ratios


def test_sharpe_is_annualised_return_over_annualised_vol():
    nav = nav_series([100, 110, 99])
    assert sharpe_ratio(nav, 0.0) == pytest.approx(
        annualised_return(nav) / annualised_volatility(nav)
    )


def test_sharpe_of_zero_vol_series_is_nan():
    assert np.isnan(sharpe_ratio(nav_series([100] * 10)))


def test_risk_free_rate_lowers_sharpe():
    nav = nav_series([100, 102, 104, 103, 106])
    assert sharpe_ratio(nav, 0.05) < sharpe_ratio(nav, 0.0)


def test_calmar_is_annualised_return_over_abs_drawdown():
    nav = nav_series([100, 110, 99, 120])
    assert calmar_ratio(nav) == pytest.approx(
        annualised_return(nav) / abs(max_drawdown(nav))
    )


# -------------------------------------------------------------- trade stats


@pytest.fixture
def round_trips():
    """Five closed trades: +100, -50, +200, -150, 0.

    accuracy       = 2 wins / 5 = 0.40   (a zero-P&L trade is NOT a win)
    gain_to_loss   = mean(100,200) / |mean(-50,-150)| = 150 / 100 = 1.50
    profit_factor  = 300 / 200 = 1.50
    """
    return pd.DataFrame({"realised_pnl": [100.0, -50.0, 200.0, -150.0, 0.0]})


def test_accuracy_hand_computed(round_trips):
    assert accuracy(round_trips) == pytest.approx(0.40)


def test_gain_to_loss_hand_computed(round_trips):
    assert gain_to_loss_ratio(round_trips) == pytest.approx(1.50)


def test_profit_factor_hand_computed(round_trips):
    assert profit_factor(round_trips) == pytest.approx(1.50)


def test_gain_to_loss_with_no_losers_is_infinite():
    assert gain_to_loss_ratio(pd.DataFrame({"realised_pnl": [10.0, 20.0]})) == float("inf")


def test_gain_to_loss_with_no_winners_is_zero():
    assert gain_to_loss_ratio(pd.DataFrame({"realised_pnl": [-10.0, -20.0]})) == 0.0


def test_metrics_on_empty_trade_table_are_nan_not_crash():
    empty = pd.DataFrame({"realised_pnl": []})
    assert np.isnan(accuracy(empty))
    assert np.isnan(gain_to_loss_ratio(empty))


def test_trade_stats_counts_and_costs():
    trades = pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-04"] * 3),
            "ticker": ["A", "B", "A"],
            "side": ["BUY", "BUY", "SELL"],
            "shares": [10, 20, 10],
            "price": [100.0, 50.0, 110.0],
            "notional": [1000.0, 1000.0, 1100.0],
            "cost": [1.0, 1.0, 1.1],
        }
    )
    stats = trade_stats(trades, pd.DataFrame({"realised_pnl": [99.0]}))
    assert stats["n_executions"] == 3
    assert stats["n_buys"] == 2
    assert stats["n_sells"] == 1
    assert stats["n_unique_stocks_traded"] == 2
    assert stats["total_transaction_cost_inr"] == pytest.approx(3.1)
    assert stats["total_traded_notional_inr"] == pytest.approx(3100.0)


def test_annualised_turnover_hand_computed():
    """Traded notional 2,000 against a flat NAV of 1,000 over exactly one year
    (252 trading days -> 253 NAV points).

    turnover = 2000 / (2 * 1000) / 1.0 = 1.0  - i.e. the book turned over once.
    """
    nav = nav_series([1000.0] * 253)
    trades = pd.DataFrame(
        {
            "ticker": ["A", "A"],
            "side": ["BUY", "SELL"],
            "notional": [1000.0, 1000.0],
            "cost": [1.0, 1.0],
        }
    )
    stats = trade_stats(trades, pd.DataFrame({"realised_pnl": [0.0]}), nav=nav)
    assert stats["annualised_turnover"] == pytest.approx(1.0)


def test_trade_stats_on_empty_input():
    stats = trade_stats(pd.DataFrame(), None)
    assert stats["n_executions"] == 0


def test_short_nav_series_raises():
    with pytest.raises(ValueError):
        total_return(pd.Series([100.0]))

"""
Every metric the guidelines require, computed from the backtest output.

OWNER: Person B (engine/evaluation)

Required (see docs/strategy_notes.md for exact definitions to use verbatim
in the report):
- total_return, annualised_return (geometric)
- max_drawdown
- sharpe_ratio (annualised return / std of daily returns, 0% risk-free rate)
- gain_to_loss_ratio (avg profit of winning trades / avg loss of losing trades)
- accuracy (% of trades that were profitable)
- trade_stats: total trades, trades per stock, turnover

TODO: implement each as a small pure function taking the NAV series and/or
trade log from backtest.py, so they're independently unit-testable.
"""

import pandas as pd
import numpy as np


def total_return(nav: pd.Series) -> float:
    raise NotImplementedError


def annualised_return(nav: pd.Series) -> float:
    raise NotImplementedError


def max_drawdown(nav: pd.Series) -> float:
    raise NotImplementedError


def sharpe_ratio(nav: pd.Series, risk_free_rate: float = 0.0) -> float:
    raise NotImplementedError


def gain_to_loss_ratio(trades: pd.DataFrame) -> float:
    raise NotImplementedError


def accuracy(trades: pd.DataFrame) -> float:
    raise NotImplementedError


def trade_stats(trades: pd.DataFrame) -> dict:
    raise NotImplementedError


def all_metrics(nav: pd.Series, trades: pd.DataFrame, risk_free_rate: float = 0.0) -> dict:
    return {
        "total_return": total_return(nav),
        "annualised_return": annualised_return(nav),
        "max_drawdown": max_drawdown(nav),
        "sharpe_ratio": sharpe_ratio(nav, risk_free_rate),
        "gain_to_loss_ratio": gain_to_loss_ratio(trades),
        "accuracy": accuracy(trades),
        "trade_stats": trade_stats(trades),
    }

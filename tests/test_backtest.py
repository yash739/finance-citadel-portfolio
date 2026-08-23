"""
Correctness tests for the backtest engine, on a tiny synthetic example where
the expected NAV can be hand-checked. Get this passing before trusting any
number computed on real data.

TODO (Person B):
- Build a toy universe of 2-3 fake tickers with a handful of made-up daily
  prices over ~10-20 days and one or two rebalance dates.
- Hand-compute the expected NAV path (including 0.1% transaction cost on
  each buy/sell) and assert run_backtest() matches it.
- Add a test that a portfolio never exceeds config.universe.max_holdings
  positions at any point in time.
- Add a test that weights always sum to <=1 (allowing for cash drag) after
  weight_stocks(), and no single weight exceeds max_weight_per_stock.
"""

import pytest


def test_backtest_toy_example():
    pytest.skip("TODO: implement once backtest.run_backtest is written")

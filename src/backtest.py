"""
Event-driven portfolio accounting: apply the rebalance rule through time,
track cash + holdings + NAV, and charge transaction costs on every trade.

OWNER: Person B (engine/evaluation) — this is the module correctness matters
most for. A bug here silently invalidates every downstream metric.

TODO:
- run_backtest(prices, universe, config): iterate over rebalance dates
  (config.rebalance.frequency), at each date call factors.composite_score(...)
  -> portfolio.select_stocks(...) -> portfolio.weight_stocks(...), compute the
  trades needed to move from current holdings to target weights, charge
  config.costs.transaction_cost_pct on the notional value of every buy AND
  sell, and carry the portfolio forward in NAV terms between rebalances using
  daily prices.
- Return a daily NAV series plus a trade log (date, ticker, side, shares,
  price, cost) — metrics.py and the report both need the trade log, not just
  the NAV curve, to compute accuracy / gain-to-loss / turnover.
- Write this against tests/test_backtest.py FIRST on a tiny synthetic
  example (2-3 fake stocks, a few days) where you can hand-check the expected
  NAV — do not trust it on real data until the toy case is exactly right.
- Run twice: once over dates.backtest_start..backtest_end, once over
  dates.out_of_sample_start..out_of_sample_end, with NO refitting between runs
  — same rule, same weights logic, just a different date window.
"""

import pandas as pd


def run_backtest(prices: pd.DataFrame, universe: pd.DataFrame, config: dict) -> dict:
    """Returns {"nav": pd.Series, "trades": pd.DataFrame, "weights_history": pd.DataFrame}."""
    raise NotImplementedError

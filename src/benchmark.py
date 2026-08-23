"""
Benchmark comparison series (Nifty 100 or Nifty 500) over the same window.

OWNER: Person B (engine/evaluation)

TODO:
- load_benchmark(prices, ticker): extract + normalise the benchmark to the
  same starting capital as the portfolio (₹1 crore) so equity curves are
  directly comparable on one chart.
- relative_metrics(portfolio_nav, benchmark_nav): excess return, tracking
  error, information ratio if time permits — at minimum, plot both curves
  together and report the return differential.
"""

import pandas as pd


def load_benchmark(prices: pd.DataFrame, ticker: str, starting_capital: float) -> pd.Series:
    raise NotImplementedError

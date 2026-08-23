"""
Turn factor scores into an actual portfolio: which stocks, what weights.

OWNER: Person A (data/strategy), consumed by Person B's backtest.py

TODO:
- select_stocks(scores, max_holdings=10): rank by composite score, take the
  top N (<=10). Consider a small buffer/hysteresis rule (e.g. a held stock
  only gets dropped if it falls out of the top ~15) to reduce needless
  turnover/transaction-cost churn between rebalances — document if you use one.
- weight_stocks(selected, scores, scheme, max_weight_per_stock):
    - "equal_weight": 1/N each
    - "score_proportional": weight ∝ composite score (renormalised, capped)
    - "inverse_vol": weight ∝ 1/volatility (renormalised, capped)
  Apply max_weight_per_stock from config.yaml as a hard cap, renormalise after.
- Keep this function pure (scores in, target weights out) so backtest.py can
  call it fresh at every rebalance date without side effects.
"""

import pandas as pd


def select_stocks(scores: pd.Series, max_holdings: int = 10) -> list[str]:
    raise NotImplementedError


def weight_stocks(
    selected: list[str],
    scores: pd.Series,
    scheme: str = "score_proportional",
    max_weight_per_stock: float = 0.25,
) -> pd.Series:
    raise NotImplementedError

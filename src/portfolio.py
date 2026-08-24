"""
Turn factor scores into an actual portfolio: which stocks, what weights.

OWNER: Person A (data/strategy), consumed by Person B's backtest.py

Both functions here are PURE - scores in, target weights out, no side effects and no
reads from disk - so backtest.py can call them fresh at every rebalance date and so
they are trivially unit-testable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def select_stocks(
    scores: pd.Series,
    max_holdings: int = 10,
    current_holdings=None,
    buffer_rank=None,
) -> list:
    """Rank by composite score and take the top N (<= max_holdings).

    HYSTERESIS (the `buffer_rank` argument): without it, a stock oscillating between
    rank 10 and rank 11 is sold and rebought every month, paying 0.1% each way for no
    change in exposure. With `buffer_rank=15`, a name already held is only dropped once
    it falls out of the top 15. New entrants must still crack the top `max_holdings`.

    This is a turnover-reduction rule, not a return-seeking one, and it is applied
    identically in the in-sample and out-of-sample runs.
    """
    valid = scores.dropna().sort_values(ascending=False)
    if valid.empty:
        return []

    if not current_holdings or not buffer_rank:
        return list(valid.index[:max_holdings])

    buffer_rank = max(int(buffer_rank), int(max_holdings))
    keep_zone = set(valid.index[:buffer_rank])

    # Survivors keep their slots, in score order.
    survivors = [t for t in valid.index if t in current_holdings and t in keep_zone]
    survivors = survivors[:max_holdings]

    # Fill remaining slots from the top of the ranking.
    selected = list(survivors)
    for t in valid.index[:max_holdings]:
        if len(selected) >= max_holdings:
            break
        if t not in selected:
            selected.append(t)

    # Order the final book by score so downstream output is deterministic.
    return [t for t in valid.index if t in set(selected)]


def _cap_and_renormalise(w: pd.Series, cap: float) -> pd.Series:
    """Apply a per-name cap, pushing the excess onto uncapped names, until stable.

    A single pass is not enough: redistributing excess can push another name over the
    cap. Iterate to a fixed point.

    If n_names * cap < 1 the book CANNOT be fully invested under the cap - we return
    weights summing to n*cap and let the caller hold the remainder as cash, rather
    than silently breaching the risk limit.
    """
    if w.empty:
        return w
    w = w.clip(lower=0.0)
    if w.sum() <= 0:
        w = pd.Series(1.0 / len(w), index=w.index)
    w = w / w.sum()

    if len(w) * cap <= 1.0:
        return pd.Series(cap, index=w.index)

    for _ in range(100):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        under = ~over
        headroom = (cap - w[under]).clip(lower=0.0)
        if headroom.sum() <= 1e-12:
            break
        w[under] = w[under] + excess * (headroom / headroom.sum())

    return w / w.sum() if w.sum() > 0 else w


def weight_stocks(
    selected: list,
    scores: pd.Series,
    scheme: str = "score_proportional",
    max_weight_per_stock: float = 0.25,
    volatilities=None,
) -> pd.Series:
    """Target weights for `selected`, capped at `max_weight_per_stock`.

    Schemes:
      equal_weight        1/N each.
      score_proportional  weight increasing in composite score, via cross-sectional
                          RANK among the selected names.
      inverse_vol         weight proportional to 1/realised volatility.

    WHY score_proportional USES RANKS: the composite score is a z-score, so it is
    signed and centred on zero. Literal weight-proportional-to-score is undefined
    when a score is negative (negative weights = short positions, which this
    long-only mandate forbids) and explodes when a score is near zero. Ranks are
    monotone in score, always positive, and scale-free. The alternative - shifting
    all scores positive by subtracting the minimum - makes every weight depend on
    whichever single worst name happens to be in the book that month, which is
    strictly worse behaviour. Documented here because it is a real modelling
    decision, not an implementation detail.
    """
    if not selected:
        return pd.Series(dtype=float)

    sel = pd.Index(selected)
    n = len(sel)

    if scheme == "equal_weight":
        raw = pd.Series(1.0 / n, index=sel)

    elif scheme == "score_proportional":
        s = scores.reindex(sel)
        # Rank 1 = worst of the selected, rank n = best. All strictly positive.
        raw = s.rank(method="average", ascending=True)
        if raw.isna().any():
            raw = raw.fillna(raw.mean() if raw.notna().any() else 1.0)

    elif scheme == "inverse_vol":
        if volatilities is None:
            raise ValueError("inverse_vol weighting requires `volatilities`")
        v = pd.Series(volatilities).reindex(sel).astype(float)
        v = v.replace(0.0, np.nan)
        if v.notna().sum() == 0:
            raw = pd.Series(1.0 / n, index=sel)
        else:
            v = v.fillna(v.max())
            raw = 1.0 / v

    else:
        raise ValueError(
            "unknown weighting_scheme %r - expected one of "
            "equal_weight, score_proportional, inverse_vol" % scheme
        )

    return _cap_and_renormalise(raw.astype(float), float(max_weight_per_stock))

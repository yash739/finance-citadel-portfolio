"""Shared fixtures: a small, fully deterministic synthetic market."""

import numpy as np
import pandas as pd
import pytest

TICKERS = ["AAA.NS", "BBB.NS", "CCC.NS", "DDD.NS"]


def make_prices(n_days=400, seed=7, start="2020-01-01"):
    """Four stocks with deliberately different drift, plus a benchmark.

    Deterministic (fixed seed) so every assertion in the suite is reproducible.
    Drifts are ordered AAA > BBB > CCC > DDD so momentum ranking is predictable,
    and each series carries genuine noise so the volatility factor is well-defined
    (a perfectly flat series would score NaN by design - see factors.low_vol_score).
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, periods=n_days)
    drifts = {"AAA.NS": 0.0012, "BBB.NS": 0.0006, "CCC.NS": 0.0001, "DDD.NS": -0.0004}

    data = {}
    for t, mu in drifts.items():
        shocks = rng.normal(mu, 0.012, size=n_days)
        data[t] = 100.0 * np.exp(np.cumsum(shocks))

    bench = rng.normal(0.0004, 0.008, size=n_days)
    data["^CNX100"] = 15000.0 * np.exp(np.cumsum(bench))

    return pd.DataFrame(data, index=dates)


def make_volumes(prices, per_day=5_000_000):
    """Volume large enough that the liquidity filter passes everything by default."""
    return pd.DataFrame(per_day, index=prices.index, columns=prices.columns)


def make_universe(tickers=TICKERS):
    return pd.DataFrame(
        {
            "ticker": tickers,
            "name": [t.replace(".NS", " Ltd") for t in tickers],
            "sector": ["Test"] * len(tickers),
            "indices": [["Nifty 100"]] * len(tickers),
        }
    )


def make_config(**overrides):
    cfg = {
        "capital": {"starting_value_inr": 1_000_000.0},
        "universe": {"max_holdings": 2, "sources": []},
        "dates": {},
        "costs": {"transaction_cost_pct": 0.001},
        "factors": {
            "momentum_lookback_months": 6,
            "momentum_skip_months": 1,
            "low_vol_lookback_months": 3,
            "liquidity_lookback_months": 1,
            "min_avg_daily_turnover_inr": 0.0,
            "weights": {"momentum": 0.5, "low_vol": 0.5},
        },
        "rebalance": {
            "frequency": "M",
            "weighting_scheme": "equal_weight",
            "max_weight_per_stock": 0.6,
            "buffer_rank": None,
        },
        "benchmark": {"ticker": "^CNX100", "name": "Test Index"},
        "risk_free_rate": 0.0,
    }
    for key, val in overrides.items():
        if isinstance(val, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(val)
        else:
            cfg[key] = val
    return cfg


@pytest.fixture
def prices():
    return make_prices()


@pytest.fixture
def volumes(prices):
    return make_volumes(prices)


@pytest.fixture
def universe():
    return make_universe()


@pytest.fixture
def config():
    return make_config()

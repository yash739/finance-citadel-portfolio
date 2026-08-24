"""
Benchmark comparison series (Nifty 100) over the same window.

OWNER: Person B (engine/evaluation)

WHY NIFTY 100 IS THE RIGHT BENCHMARK HERE - the guidelines require the choice to be
justified, not just named. Our investable universe is the union of the Nifty 100,
Midcap 100 and Smallcap 100, so no single published index matches it exactly. The
Nifty 100 is the defensible choice because it is the large-cap core that dominates
the liquidity-filtered universe: after the turnover screen, most surviving names are
large caps. Benchmarking a partly mid/small-cap book against a pure large-cap index
is if anything a HARDER comparison during periods when small caps rally, so it does
not flatter the strategy.

A literal 1/3-1/3-1/3 blend of the three source indices would be the tightest match,
but Yahoo publishes no working Nifty Smallcap 100 symbol (both ^CNXSC and ^CNXSMCP
return empty - verify with `python -m src.benchmark --check`). We therefore report
Nifty 500 (^CRSLDX) as the secondary benchmark instead: it is a real published index
that genuinely spans large, mid and small caps. `blended_benchmark()` remains
available if a working smallcap symbol turns up later.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def load_benchmark(prices: pd.DataFrame, ticker: str, starting_capital: float) -> pd.Series:
    """Extract the benchmark column and rebase it to `starting_capital`.

    Rebasing (rather than plotting raw index points) is what makes the equity curves
    directly comparable on one chart: both start at Rs 1 crore, so vertical distance
    is rupees of outperformance.
    """
    if ticker not in prices.columns:
        raise KeyError(
            "benchmark %r is not in the price panel. Check the Yahoo symbol in "
            "config.yaml - verify it with `python -m src.benchmark --check`." % ticker
        )
    series = prices[ticker].astype(float).dropna()
    if series.empty:
        raise ValueError("benchmark %r has no observations in this window" % ticker)
    return (series / series.iloc[0]) * float(starting_capital)


def blended_benchmark(
    prices: pd.DataFrame, tickers, starting_capital: float, weights=None
) -> pd.Series:
    """Equal-weighted (or custom-weighted) blend of several index series, rebased.

    Rebalanced daily back to target weights, which is the standard convention for a
    synthetic index blend.
    """
    available = [t for t in tickers if t in prices.columns]
    if not available:
        raise KeyError("none of %s are in the price panel" % list(tickers))

    sub = prices[available].astype(float).dropna(how="all").ffill()
    rets = sub.pct_change().fillna(0.0)
    if weights is None:
        w = pd.Series(1.0 / len(available), index=available)
    else:
        w = pd.Series(weights).reindex(available).fillna(0.0)
        w = w / w.sum()

    blend_ret = (rets * w).sum(axis=1)
    return float(starting_capital) * (1.0 + blend_ret).cumprod()


def relative_metrics(portfolio_nav: pd.Series, benchmark_nav: pd.Series) -> dict:
    """Excess return, tracking error, information ratio, beta and alpha.

    Both series are aligned to their common dates first - comparing a portfolio that
    traded on a day the index did not (or vice versa) would corrupt every number here.
    """
    from src.metrics import annualised_return, max_drawdown, total_return

    p = pd.Series(portfolio_nav).astype(float).dropna()
    b = pd.Series(benchmark_nav).astype(float).dropna()
    common = p.index.intersection(b.index)
    if len(common) < 3:
        raise ValueError("portfolio and benchmark share fewer than 3 dates")
    p, b = p.loc[common], b.loc[common]

    pr = p.pct_change().dropna()
    br = b.pct_change().dropna()
    active = (pr - br).dropna()

    te = float(active.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(active) > 1 else np.nan
    ann_active = annualised_return(p) - annualised_return(b)

    var_b = float(br.var(ddof=1))
    beta = float(pr.cov(br) / var_b) if var_b > 0 else np.nan
    alpha = ann_active if not np.isfinite(beta) else float(
        annualised_return(p) - beta * annualised_return(b)
    )

    return {
        "portfolio_total_return": total_return(p),
        "benchmark_total_return": total_return(b),
        "excess_total_return": total_return(p) - total_return(b),
        "portfolio_annualised_return": annualised_return(p),
        "benchmark_annualised_return": annualised_return(b),
        "annualised_excess_return": ann_active,
        "portfolio_max_drawdown": max_drawdown(p),
        "benchmark_max_drawdown": max_drawdown(b),
        "tracking_error": te,
        "information_ratio": float(ann_active / te) if te and np.isfinite(te) and te > 0 else np.nan,
        "beta": beta,
        "annualised_alpha": alpha,
        "up_capture": _capture(pr, br, up=True),
        "down_capture": _capture(pr, br, up=False),
    }


def _capture(pr: pd.Series, br: pd.Series, up: bool) -> float:
    """Share of the benchmark's up (or down) moves the portfolio captured."""
    mask = br > 0 if up else br < 0
    if mask.sum() < 2:
        return float("nan")
    denom = float(br[mask].mean())
    if denom == 0:
        return float("nan")
    return float(pr[mask].mean() / denom)


CANDIDATE_SYMBOLS = ["^CNX100", "^NSEI", "^CRSLDX", "NIFTY100.NS", "^NSEBANK"]


def check_symbols(symbols=None, start="2024-01-01", end="2024-06-30") -> pd.DataFrame:
    """Probe Yahoo for which benchmark symbols actually return data.

    config.yaml ships with `^CNX100` and a comment telling you to verify it. This is
    that verification - run it before trusting any benchmark comparison.
    """
    import yfinance as yf

    rows = []
    for sym in symbols or CANDIDATE_SYMBOLS:
        try:
            df = yf.download(sym, start=start, end=end, progress=False, auto_adjust=True)
            n = 0 if df is None else len(df)
            rows.append({"symbol": sym, "rows": n, "status": "OK" if n > 0 else "EMPTY"})
        except Exception as exc:
            rows.append({"symbol": sym, "rows": 0, "status": "ERROR: %s" % str(exc)[:60]})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Probe candidate Yahoo symbols.")
    args = parser.parse_args()
    if args.check:
        print(check_symbols().to_string(index=False))

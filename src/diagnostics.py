"""
Bias diagnostics: how much of the backtest result is real, and how much is artifact?

OWNER: shared - this is the module that decides whether the headline number is
honest, so both of us should understand it.

Run:  python -m src.diagnostics

THE PROBLEM THIS EXISTS TO MEASURE
Our universe is a single snapshot of index membership taken in 2026 and applied
backwards to 2021. Index promotion follows good performance, so the 2026 Nifty
Smallcap 100 is, by construction, a list of stocks that went up over 2021-2025. Any
strategy run on that list inherits a large forward-looking advantage that has nothing
to do with the strategy.

HOW WE MEASURE IT
Equal-weight buy-and-hold across the entire snapshot universe. No factors, no
selection, no timing - zero skill. Whatever that portfolio earns above the published
index is the size of the survivorship distortion, because a skill-free portfolio
cannot generate alpha. That gives a three-way decomposition of the headline result:

    published index return          the honest market baseline
    + survivorship bias             EW-hold-the-snapshot MINUS the index
    + strategy selection            the full strategy MINUS EW-hold-the-snapshot

Only the third line is attributable to the strategy. It is also the only line that
should be expected to persist out-of-sample.

USE `equal_weight_universe()` AS THE FAIR BENCHMARK. Comparing the strategy against
the Nifty 100 flatters it by roughly 20 percentage points a year. Comparing it against
an equal-weight portfolio of its OWN universe holds the bias constant on both sides of
the comparison and isolates what the factor model actually contributed.
"""

from __future__ import annotations

import pandas as pd

from src.metrics import annualised_return, max_drawdown, sharpe_ratio, total_return


def equal_weight_universe(
    prices: pd.DataFrame, tickers, starting_capital: float
) -> pd.Series:
    """Equal-weight, daily-rebalanced buy-and-hold across `tickers`.

    Names absent on a given day (not yet listed, or delisted) are simply excluded from
    that day's average rather than treated as a zero return, so a late IPO does not
    drag the series down before it existed.

    This is the skill-free portfolio: it holds everything, forever, in equal size.
    """
    cols = [t for t in tickers if t in prices.columns]
    if not cols:
        raise KeyError("none of the requested tickers are in the price panel")
    rets = prices[cols].astype(float).pct_change()
    equal = rets.mean(axis=1, skipna=True).fillna(0.0)
    return float(starting_capital) * (1.0 + equal).cumprod()


def summarise(nav: pd.Series) -> dict:
    return {
        "total_return": total_return(nav),
        "annualised_return": annualised_return(nav),
        "sharpe_ratio": sharpe_ratio(nav),
        "max_drawdown": max_drawdown(nav),
    }


def decompose(
    strategy_nav: pd.Series,
    universe_nav: pd.Series,
    index_nav: pd.Series,
) -> dict:
    """Split the strategy's excess return into bias and selection, in CAGR terms."""
    idx = annualised_return(index_nav)
    uni = annualised_return(universe_nav)
    strat = annualised_return(strategy_nav)
    excess = strat - idx
    bias = uni - idx
    selection = strat - uni
    return {
        "index_cagr": idx,
        "universe_ew_cagr": uni,
        "strategy_cagr": strat,
        "total_excess_over_index": excess,
        "attributable_to_survivorship_bias": bias,
        "attributable_to_strategy_selection": selection,
        "bias_share_of_excess": (bias / excess) if excess not in (0, None) else float("nan"),
        "strategy_beats_own_universe": bool(selection > 0),
    }


def _fmt_row(name, nav):
    s = summarise(nav)
    return "%-44s %9.1f%% %7.1f%% %8.2f %7.1f%%" % (
        name,
        s["total_return"] * 100,
        s["annualised_return"] * 100,
        s["sharpe_ratio"],
        s["max_drawdown"] * 100,
    )


def run_report(config_path: str = "config.yaml") -> dict:
    """Print the full bias decomposition for both run windows."""
    import yaml

    from src.backtest import run_backtest
    from src.benchmark import load_benchmark
    from src.universe import load_universe

    config = yaml.safe_load(open(config_path))
    capital = config["capital"]["starting_value_inr"]

    prices = pd.read_parquet("data/processed/prices.parquet")
    prices.index = pd.to_datetime(prices.index)
    volumes = pd.read_parquet("data/processed/volumes.parquet")
    volumes.index = pd.to_datetime(volumes.index)

    universe = load_universe(config["universe"]["sources"])
    bench_ticker = config["benchmark"]["ticker"]

    out = {}
    windows = {
        "in_sample": (config["dates"]["backtest_start"], config["dates"]["backtest_end"]),
        "out_of_sample": (config["dates"]["out_of_sample_start"], config["dates"]["out_of_sample_end"]),
    }

    for label, (start, end) in windows.items():
        win = prices.loc[start:end]
        if win.empty:
            continue
        vwin = volumes.loc[start:end]
        hist = prices.loc[:start].iloc[:-1]
        vhist = volumes.loc[:start].iloc[:-1]

        result = run_backtest(win, universe, config, volumes=vwin,
                              history=hist, volume_history=vhist)
        strat_nav = result["nav"]
        uni_nav = equal_weight_universe(win, universe["ticker"], capital)
        idx_nav = load_benchmark(win, bench_ticker, capital)

        print("\n" + "=" * 82)
        print("%-44s %10s %8s %8s %8s"
              % (label.replace("_", " ").upper(), "TotalRet", "CAGR", "Sharpe", "MaxDD"))
        print("-" * 82)
        print(_fmt_row("Strategy (10 names, factor-selected)", strat_nav))
        print(_fmt_row("Equal-weight hold of SAME universe", uni_nav))
        print(_fmt_row("%s index" % config["benchmark"]["name"], idx_nav))

        d = decompose(strat_nav, uni_nav, idx_nav)
        print("-" * 82)
        print("  Excess over index                     %+7.1f pp/yr" % (d["total_excess_over_index"] * 100))
        print("    ...of which survivorship bias       %+7.1f pp/yr   <-- NOT strategy alpha"
              % (d["attributable_to_survivorship_bias"] * 100))
        print("    ...of which factor selection        %+7.1f pp/yr"
              % (d["attributable_to_strategy_selection"] * 100))
        verdict = "YES" if d["strategy_beats_own_universe"] else "NO - it underperforms it"
        print("  Strategy beats its own universe?      %s" % verdict)
        out[label] = d

    print("\n" + "=" * 82)
    print("Read the 'factor selection' line as the strategy's real contribution.")
    print("The survivorship line is an artifact of the static constituent snapshot")
    print("and must be disclosed in the report - see src/universe.py.")
    return out


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--json-out", default="reports/bias_decomposition.json")
    args = parser.parse_args()

    result = run_report(args.config)
    if args.json_out and result:
        from pathlib import Path

        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json_out, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print("Wrote %s" % args.json_out)

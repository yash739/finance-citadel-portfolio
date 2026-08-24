"""
Main entry point: config -> data -> factors -> portfolio -> backtest -> metrics -> report assets.

Run: python run_backtest.py --config config.yaml

Runs the SAME rule over two windows with no refitting between them:
  in_sample      2021-01-01 .. 2025-12-31   (the backtest)
  out_of_sample  2026-01-01 .. 2026-06-30   (the held-out stress test)

Each window gets warm-up price history spliced in front of it so the 12-month momentum
factor is computable on its very first trading day. Warm-up data is scored on but never
traded and never contributes to NAV - without it the first year of each run would be
silently unscoreable, and the out-of-sample window (only ~6 months long) would produce
no trades at all.
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from src.backtest import run_backtest
from src.benchmark import load_benchmark, relative_metrics
from src.diagnostics import decompose, equal_weight_universe
from src.metrics import all_metrics
from src.universe import load_universe
from src.visualize import make_all_figures

PROCESSED = Path("data/processed")
REPORTS = Path("reports")


def _load_panels():
    price_path = PROCESSED / "prices.parquet"
    if not price_path.exists():
        raise SystemExit(
            "data/processed/prices.parquet not found.\n"
            "Build it first:  python -m src.data_loader"
        )
    prices = pd.read_parquet(price_path)
    vol_path = PROCESSED / "volumes.parquet"
    volumes = pd.read_parquet(vol_path) if vol_path.exists() else None
    prices.index = pd.to_datetime(prices.index)
    if volumes is not None:
        volumes.index = pd.to_datetime(volumes.index)
    return prices.sort_index(), (volumes.sort_index() if volumes is not None else None)


def _fmt_inr(x):
    """Rupees in crore/lakh - the units the report is written in."""
    if x is None or pd.isna(x):
        return "n/a"
    if abs(x) >= 1e7:
        return "Rs %.2f Cr" % (x / 1e7)
    if abs(x) >= 1e5:
        return "Rs %.2f L" % (x / 1e5)
    return "Rs %.0f" % x


def _print_summary(label, metrics, rel):
    ts = metrics["trade_stats"]
    print("\n" + "=" * 66)
    print("  %s" % label.replace("_", " ").upper())
    print("=" * 66)
    print("  Total Net PNL          %s   <-- primary metric" % _fmt_inr(metrics["total_net_pnl_inr"]))
    print("  Final NAV              %s" % _fmt_inr(metrics["final_nav_inr"]))
    print("  Total return           %7.2f%%" % (metrics["total_return"] * 100))
    print("  Annualised return      %7.2f%%" % (metrics["annualised_return"] * 100))
    print("  Annualised volatility  %7.2f%%" % (metrics["annualised_volatility"] * 100))
    print("  Sharpe ratio           %7.2f" % metrics["sharpe_ratio"])
    print("  Sortino ratio          %7.2f" % metrics["sortino_ratio"])
    print("  Max drawdown           %7.2f%%" % (metrics["max_drawdown"] * 100))
    print("  Accuracy               %7.2f%%  (%d closed round trips)"
          % (metrics["accuracy"] * 100 if pd.notna(metrics["accuracy"]) else float("nan"),
             ts["n_round_trips"]))
    print("  Gain-to-loss ratio     %7.2f" % metrics["gain_to_loss_ratio"])
    print("  Annualised turnover    %7.2fx" % ts["annualised_turnover"])
    print("  Transaction costs paid %s" % _fmt_inr(ts["total_transaction_cost_inr"]))
    print("  Executions             %7d  (%d buys / %d sells, %d unique stocks)"
          % (ts["n_executions"], ts["n_buys"], ts["n_sells"], ts["n_unique_stocks_traded"]))
    if rel:
        print("  ---- vs %s ----" % rel.get("_benchmark_name", "benchmark"))
        print("  Benchmark return       %7.2f%%" % (rel["benchmark_total_return"] * 100))
        print("  Excess return          %7.2f%%" % (rel["excess_total_return"] * 100))
        print("  Information ratio      %7.2f" % rel["information_ratio"])
        print("  Beta                   %7.2f" % rel["beta"])

    d = metrics.get("bias_decomposition")
    if d:
        print("  ---- honesty check: where the excess came from ----")
        print("  Excess over index      %+7.2f pp/yr" % (d["total_excess_over_index"] * 100))
        print("    survivorship bias    %+7.2f pp/yr   <-- artifact, not alpha"
              % (d["attributable_to_survivorship_bias"] * 100))
        print("    factor selection     %+7.2f pp/yr   <-- the real contribution"
              % (d["attributable_to_strategy_selection"] * 100))
        if not d["strategy_beats_own_universe"]:
            print("  WARNING: the strategy UNDERPERFORMS an equal-weight hold of its")
            print("           own universe. The factor model is subtracting value here.")


def main(config_path: str, skip_figures: bool = False):
    with open(config_path) as f:
        config = yaml.safe_load(f)

    universe = load_universe(config["universe"]["sources"])
    prices, volumes = _load_panels()
    capital = config["capital"]["starting_value_inr"]
    bench_ticker = config["benchmark"]["ticker"]

    print("Universe: %d tickers | price panel: %d days x %d columns (%s .. %s)"
          % (len(universe), prices.shape[0], prices.shape[1],
             prices.index.min().date(), prices.index.max().date()))

    REPORTS.mkdir(exist_ok=True)
    figures_dir = REPORTS / "figures"
    windows = {
        "in_sample": (config["dates"]["backtest_start"], config["dates"]["backtest_end"]),
        "out_of_sample": (config["dates"]["out_of_sample_start"], config["dates"]["out_of_sample_end"]),
    }

    summary = {}
    for label, (start, end) in windows.items():
        window_prices = prices.loc[start:end]
        if window_prices.empty:
            print("\n[%s] no price data in %s..%s - skipping." % (label, start, end))
            continue

        window_volumes = volumes.loc[start:end] if volumes is not None else None
        # Everything strictly before the window is warm-up: scored on, never traded.
        history = prices.loc[:start].iloc[:-1] if start in prices.index else prices.loc[:start]
        vol_history = (volumes.loc[:start].iloc[:-1] if volumes is not None and start in volumes.index
                       else (volumes.loc[:start] if volumes is not None else None))

        print("\n[%s] %s .. %s  (%d trading days, %d days warm-up)"
              % (label, start, end, len(window_prices), len(history)))

        result = run_backtest(
            window_prices, universe, config,
            volumes=window_volumes, history=history, volume_history=vol_history,
        )
        metrics = all_metrics(
            result["nav"], result["trades"],
            risk_free_rate=config["risk_free_rate"],
            round_trips=result["round_trips"],
            starting_capital=capital,
        )

        rel = None
        benchmark_nav = None
        try:
            benchmark_nav = load_benchmark(window_prices, bench_ticker, capital)
            rel = relative_metrics(result["nav"], benchmark_nav)
            rel["_benchmark_name"] = config["benchmark"]["name"]
            metrics["benchmark"] = rel
        except (KeyError, ValueError) as exc:
            print("  benchmark comparison unavailable: %s" % exc)

        # The FAIR benchmark: an equal-weight hold of our own universe. It carries the
        # identical survivorship bias, so comparing against it isolates what the factor
        # model actually contributed. See src/diagnostics.py.
        try:
            ew_nav = equal_weight_universe(window_prices, universe["ticker"], capital)
            ew_rel = relative_metrics(result["nav"], ew_nav)
            ew_rel["_benchmark_name"] = "Equal-weight own universe (bias-matched)"
            metrics["benchmark_equal_weight_universe"] = ew_rel
            metrics["bias_decomposition"] = decompose(result["nav"], ew_nav, benchmark_nav) \
                if benchmark_nav is not None else None
        except (KeyError, ValueError) as exc:
            print("  equal-weight universe benchmark unavailable: %s" % exc)

        secondary = config["benchmark"].get("secondary_ticker")
        if secondary:
            try:
                sec_nav = load_benchmark(window_prices, secondary, capital)
                sec_rel = relative_metrics(result["nav"], sec_nav)
                sec_rel["_benchmark_name"] = config["benchmark"].get("secondary_name", secondary)
                metrics["benchmark_secondary"] = sec_rel
            except (KeyError, ValueError) as exc:
                print("  secondary benchmark unavailable: %s" % exc)

        if not skip_figures:
            make_all_figures(result, benchmark_nav, str(figures_dir), label)

        with open(REPORTS / ("metrics_%s.json" % label), "w") as f:
            json.dump(metrics, f, indent=2, default=str)
        result["trades"].to_csv(REPORTS / ("trades_%s.csv" % label), index=False)
        result["round_trips"].to_csv(REPORTS / ("round_trips_%s.csv" % label), index=False)
        result["open_positions"].to_csv(REPORTS / ("open_positions_%s.csv" % label), index=False)
        result["nav"].to_csv(REPORTS / ("nav_%s.csv" % label))

        _print_summary(label, metrics, rel)
        summary[label] = metrics

    if summary:
        with open(REPORTS / "metrics_summary.json", "w") as f:
            json.dump(summary, f, indent=2, default=str)
        print("\nWrote metrics, trade logs and figures to %s/" % REPORTS)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--skip-figures", action="store_true")
    args = parser.parse_args()
    main(args.config, skip_figures=args.skip_figures)

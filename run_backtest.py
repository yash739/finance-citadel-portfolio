"""
Main entry point: config -> data -> factors -> portfolio -> backtest -> metrics -> report assets.

Run: python run_backtest.py --config config.yaml
"""

import argparse
import json
import yaml
import pandas as pd
from pathlib import Path

from src.universe import load_universe
from src.backtest import run_backtest
from src.metrics import all_metrics
from src.benchmark import load_benchmark
from src.visualize import plot_equity_curve


def main(config_path: str):
    with open(config_path) as f:
        config = yaml.safe_load(f)

    universe = load_universe(config["universe"]["sources"])
    prices = pd.read_parquet("data/processed/prices.parquet")

    for label, (start, end) in {
        "in_sample": (config["dates"]["backtest_start"], config["dates"]["backtest_end"]),
        "out_of_sample": (config["dates"]["out_of_sample_start"], config["dates"]["out_of_sample_end"]),
    }.items():
        window_prices = prices.loc[start:end]
        result = run_backtest(window_prices, universe, config)
        metrics = all_metrics(result["nav"], result["trades"], config["risk_free_rate"])

        benchmark_nav = load_benchmark(window_prices, config["benchmark"]["ticker"], config["capital"]["starting_value_inr"])
        plot_equity_curve(result["nav"], benchmark_nav, f"reports/figures/equity_curve_{label}.png")

        out_dir = Path("reports")
        out_dir.mkdir(exist_ok=True)
        with open(out_dir / f"metrics_{label}.json", "w") as f:
            json.dump(metrics, f, indent=2, default=str)
        result["trades"].to_csv(out_dir / f"trades_{label}.csv", index=False)

        print(f"[{label}] {start}..{end} -> total_return={metrics['total_return']:.2%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    main(args.config)

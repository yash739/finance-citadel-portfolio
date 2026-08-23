"""
Plots for the report: equity curve vs. benchmark, drawdown, rolling returns.

OWNER: Person B (engine/evaluation)

TODO:
- plot_equity_curve(portfolio_nav, benchmark_nav, out_path)
- plot_drawdown(portfolio_nav, out_path)
- plot_rolling_returns(portfolio_nav, window_days, out_path)
Save everything to reports/figures/ at report-quality resolution (dpi>=150)
with readable axis labels — these go straight into the 5-6 page report.
"""

import matplotlib.pyplot as plt
import pandas as pd


def plot_equity_curve(portfolio_nav: pd.Series, benchmark_nav: pd.Series, out_path: str):
    raise NotImplementedError

"""
Plots for the report: equity curve vs. benchmark, drawdown, rolling returns.

OWNER: Person B (engine/evaluation)

Everything saves at dpi>=150 with readable labels, because these go straight into a
5-6 page PDF where an unreadable axis is a wasted figure. Rupee axes are formatted in
lakhs/crores rather than raw floats - "1.4 Cr" is legible, "14032188.0" is not.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display in WSL / CI
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

DPI = 160
FIGSIZE = (10, 5.5)

PORTFOLIO_COLOR = "#1f4e79"
BENCHMARK_COLOR = "#a0a0a0"
LOSS_COLOR = "#b03030"


def _inr_formatter():
    """Format rupee amounts as lakhs/crores, the units an Indian reader expects."""

    def fmt(x, _pos):
        if abs(x) >= 1e7:
            return "%.2f Cr" % (x / 1e7)
        if abs(x) >= 1e5:
            return "%.1f L" % (x / 1e5)
        return "%.0f" % x

    return mticker.FuncFormatter(fmt)


def _finish(ax, out_path: str, title: str, ylabel: str):
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_xlabel("")
    ax.grid(True, alpha=0.25, linestyle="--", linewidth=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close()
    print("  wrote %s" % out_path)


def plot_equity_curve(portfolio_nav: pd.Series, benchmark_nav, out_path: str, title=None):
    """Portfolio NAV against the rebased benchmark, both starting at Rs 1 crore."""
    fig, ax = plt.subplots(figsize=FIGSIZE)
    p = pd.Series(portfolio_nav).dropna()
    ax.plot(p.index, p.values, label="Strategy", color=PORTFOLIO_COLOR, linewidth=1.8)

    if benchmark_nav is not None and len(benchmark_nav):
        b = pd.Series(benchmark_nav).dropna()
        ax.plot(b.index, b.values, label="Benchmark", color=BENCHMARK_COLOR,
                linewidth=1.5, linestyle="--")

    ax.axhline(float(p.iloc[0]), color="black", linewidth=0.8, alpha=0.4)
    ax.yaxis.set_major_formatter(_inr_formatter())
    ax.legend(frameon=False, fontsize=10)
    _finish(ax, out_path, title or "Portfolio value vs benchmark", "Portfolio value (INR)")


def plot_drawdown(portfolio_nav: pd.Series, out_path: str, title=None):
    """Underwater plot - how deep and how long every decline was."""
    p = pd.Series(portfolio_nav).dropna().astype(float)
    dd = (p / p.cummax() - 1.0) * 100.0

    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.fill_between(dd.index, dd.values, 0, color=LOSS_COLOR, alpha=0.30)
    ax.plot(dd.index, dd.values, color=LOSS_COLOR, linewidth=1.1)

    trough = dd.idxmin()
    ax.annotate(
        "max DD %.1f%%" % dd.min(),
        xy=(trough, dd.min()),
        xytext=(10, 14),
        textcoords="offset points",
        fontsize=9,
        arrowprops=dict(arrowstyle="->", color="black", lw=0.8),
    )
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: "%.0f%%" % v))
    _finish(ax, out_path, title or "Drawdown", "Drawdown (%)")


def plot_rolling_returns(portfolio_nav: pd.Series, window_days: int, out_path: str,
                         benchmark_nav=None, title=None):
    """Rolling annualised return - shows whether performance is broad or one lucky run."""
    p = pd.Series(portfolio_nav).dropna().astype(float)
    if len(p) <= window_days:
        print("  skipping rolling-return plot: window (%d) >= series length (%d)"
              % (window_days, len(p)))
        return

    years = window_days / 252.0
    roll = ((p / p.shift(window_days)) ** (1 / years) - 1.0).dropna() * 100.0

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(roll.index, roll.values, color=PORTFOLIO_COLOR, linewidth=1.5, label="Strategy")

    if benchmark_nav is not None and len(benchmark_nav):
        b = pd.Series(benchmark_nav).dropna().astype(float)
        if len(b) > window_days:
            rb = ((b / b.shift(window_days)) ** (1 / years) - 1.0).dropna() * 100.0
            ax.plot(rb.index, rb.values, color=BENCHMARK_COLOR, linewidth=1.3,
                    linestyle="--", label="Benchmark")

    ax.axhline(0, color="black", linewidth=0.9, alpha=0.5)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: "%.0f%%" % v))
    ax.legend(frameon=False, fontsize=10)
    _finish(ax, out_path,
            title or "Rolling %d-day annualised return" % window_days,
            "Annualised return (%)")


def plot_weights_history(weights_history: pd.DataFrame, out_path: str, title=None):
    """Stacked area of portfolio weights - makes concentration and turnover visible."""
    if weights_history is None or weights_history.empty:
        print("  skipping weights plot: no weight history")
        return

    w = weights_history.fillna(0.0)
    # Too many names in the legend is unreadable; show the biggest, group the rest.
    top = w.mean().sort_values(ascending=False).head(12).index
    plot_df = w[top].copy()
    other = w.drop(columns=top, errors="ignore").sum(axis=1)
    if (other > 0).any():
        plot_df["Other"] = other

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.stackplot(plot_df.index, plot_df.T.values,
                 labels=[str(c) for c in plot_df.columns], alpha=0.85)
    ax.set_ylim(0, max(1.0, float(plot_df.sum(axis=1).max()) * 1.05))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: "%.0f%%" % (v * 100)))
    ax.legend(frameon=False, fontsize=7, ncol=4, loc="upper center",
              bbox_to_anchor=(0.5, -0.06))
    _finish(ax, out_path, title or "Portfolio weights over time", "Weight")


def plot_monthly_returns_heatmap(portfolio_nav: pd.Series, out_path: str, title=None):
    """Month-by-year grid of returns - the standard 'is this consistent?' figure."""
    p = pd.Series(portfolio_nav).dropna().astype(float)
    monthly = p.resample("ME").last().pct_change().dropna() * 100.0
    if monthly.empty:
        print("  skipping heatmap: not enough data")
        return

    grid = pd.DataFrame(
        {"year": monthly.index.year, "month": monthly.index.month, "ret": monthly.values}
    ).pivot(index="year", columns="month", values="ret")

    fig, ax = plt.subplots(figsize=(10, 0.5 * len(grid) + 2.0))
    vmax = float(np.nanmax(np.abs(grid.values))) if grid.size else 1.0
    im = ax.imshow(grid.values, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="auto")

    ax.set_xticks(range(len(grid.columns)))
    ax.set_xticklabels(["JFMAMJJASOND"[m - 1] for m in grid.columns])
    ax.set_yticks(range(len(grid.index)))
    ax.set_yticklabels(grid.index)

    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            v = grid.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, "%.1f" % v, ha="center", va="center", fontsize=8)

    fig.colorbar(im, ax=ax, label="Monthly return (%)", fraction=0.025)
    ax.grid(False)
    _finish(ax, out_path, title or "Monthly returns (%)", "")


def make_all_figures(result: dict, benchmark_nav, out_dir: str, label: str) -> None:
    """Every figure for one run window, named consistently for the report."""
    out = Path(out_dir)
    nav = result["nav"]
    plot_equity_curve(nav, benchmark_nav, str(out / ("equity_curve_%s.png" % label)),
                      title="Portfolio value vs benchmark (%s)" % label.replace("_", " "))
    plot_drawdown(nav, str(out / ("drawdown_%s.png" % label)),
                  title="Drawdown (%s)" % label.replace("_", " "))
    plot_weights_history(result.get("weights_history"),
                         str(out / ("weights_%s.png" % label)),
                         title="Portfolio weights (%s)" % label.replace("_", " "))
    plot_monthly_returns_heatmap(nav, str(out / ("monthly_returns_%s.png" % label)),
                                 title="Monthly returns %% (%s)" % label.replace("_", " "))
    if len(pd.Series(nav).dropna()) > 252:
        plot_rolling_returns(nav, 252, str(out / ("rolling_returns_%s.png" % label)),
                             benchmark_nav=benchmark_nav)

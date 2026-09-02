"""
Every metric the guidelines require, computed from the backtest output.

OWNER: Person B (engine/evaluation)

Each metric is a small pure function of the NAV series and/or the trade tables, so
each is independently unit-testable - see tests/test_metrics.py, where every one is
checked against a hand-computed value.

DEFINITIONS USED (quote these verbatim in the report so the evaluator does not have
to guess which convention we picked):

  Total Net PNL      final NAV - starting capital, in rupees, after all transaction
                     costs. This is the competition's primary metric.
  Annualised return  geometric: (final/initial)^(252/n_days) - 1. Not the arithmetic
                     mean of daily returns, which overstates compounding results.
  Max drawdown       largest peak-to-trough decline in NAV, as a negative fraction.
  Sharpe ratio       annualised return / annualised volatility, with a 0% risk-free
                     rate as the guidelines specify. Annualised volatility is the
                     daily return standard deviation scaled by sqrt(252).
  Accuracy           share of CLOSED POSITIONS with positive whole-life realised P&L.
                     A position (buy -> optional trims -> full exit) is one trade,
                     counted once - NOT once per rebalancing trim. `accuracy_by_
                     transaction` reports the finer per-sell-leg view alongside it.
  Gain-to-loss       mean realised P&L of winning positions / mean absolute realised
                     P&L of losing positions. Undefined (inf) with no losers.
  Turnover           total traded notional / (2 x average NAV), annualised - so a
                     book that fully replaces its holdings once a year reads as 1.0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def _clean_nav(nav: pd.Series) -> pd.Series:
    nav = pd.Series(nav).astype(float).dropna()
    if len(nav) < 2:
        raise ValueError("NAV series needs at least 2 observations")
    return nav


def daily_returns(nav: pd.Series) -> pd.Series:
    return _clean_nav(nav).pct_change(fill_method=None).dropna()


def total_net_pnl(nav: pd.Series, starting_capital: float = None) -> float:
    """Absolute rupee profit after costs - the competition's primary metric."""
    nav = _clean_nav(nav)
    base = float(starting_capital) if starting_capital is not None else float(nav.iloc[0])
    return float(nav.iloc[-1] - base)


def total_return(nav: pd.Series) -> float:
    nav = _clean_nav(nav)
    return float(nav.iloc[-1] / nav.iloc[0] - 1.0)


def annualised_return(nav: pd.Series) -> float:
    """Geometric (CAGR), using trading days rather than calendar days."""
    nav = _clean_nav(nav)
    n_days = len(nav) - 1
    if n_days <= 0:
        return 0.0
    growth = float(nav.iloc[-1] / nav.iloc[0])
    if growth <= 0:
        return -1.0
    return float(growth ** (TRADING_DAYS_PER_YEAR / n_days) - 1.0)


def annualised_volatility(nav: pd.Series) -> float:
    r = daily_returns(nav)
    if len(r) < 2:
        return 0.0
    return float(r.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(nav: pd.Series) -> float:
    """Largest peak-to-trough decline, as a negative fraction (-0.25 = -25%)."""
    nav = _clean_nav(nav)
    running_peak = nav.cummax()
    return float((nav / running_peak - 1.0).min())


def max_drawdown_detail(nav: pd.Series) -> dict:
    """Depth plus the peak/trough dates and recovery status - useful for the report."""
    nav = _clean_nav(nav)
    dd = nav / nav.cummax() - 1.0
    trough = dd.idxmin()
    peak = nav.loc[:trough].idxmax()
    after = nav.loc[trough:]
    recovered = after[after >= nav.loc[peak]]
    return {
        "max_drawdown": float(dd.min()),
        "peak_date": str(peak),
        "trough_date": str(trough),
        "recovery_date": str(recovered.index[0]) if len(recovered) else None,
        "recovered": bool(len(recovered)),
    }


def sharpe_ratio(nav: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Annualised return over annualised volatility, 0% risk-free per the guidelines."""
    vol = annualised_volatility(nav)
    if vol == 0 or not np.isfinite(vol):
        return float("nan")
    return float((annualised_return(nav) - risk_free_rate) / vol)


def sortino_ratio(nav: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Like Sharpe but penalising only downside deviation."""
    r = daily_returns(nav)
    downside = r[r < 0]
    if len(downside) < 2:
        return float("nan")
    dd = float(downside.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    if dd == 0:
        return float("nan")
    return float((annualised_return(nav) - risk_free_rate) / dd)


def calmar_ratio(nav: pd.Series) -> float:
    mdd = abs(max_drawdown(nav))
    if mdd == 0:
        return float("nan")
    return float(annualised_return(nav) / mdd)


def _transaction_pnl(round_trips) -> pd.Series:
    """Realised P&L of every closing transaction (each partial trim and each full
    exit is one row). This is the finest-grained view of realised P&L."""
    if round_trips is None or len(round_trips) == 0:
        return pd.Series(dtype=float)
    df = pd.DataFrame(round_trips)
    if "realised_pnl" not in df.columns:
        return pd.Series(dtype=float)
    return df["realised_pnl"].astype(float).dropna()


def _position_pnl(round_trips) -> pd.Series:
    """Whole-life realised P&L per CLOSED position episode.

    A position is bought, optionally trimmed several times, then fully sold. Each of
    those sells is a separate row in `round_trips`, all sharing one `position_id`.
    Summing realised P&L within a position_id gives the P&L of the position as a
    single trade - which is what "accuracy" and "gain-to-loss" should be measured
    over, rather than counting each monthly rebalancing trim as its own trade.

    Only positions that were fully closed (a row with closed_fully=True exists for the
    id) are included; positions still open on the final day have an unknown final
    outcome and are excluded, exactly as an open winner is excluded from accuracy.

    Falls back to per-transaction P&L for legacy trade logs that predate position_id.
    """
    if round_trips is None or len(round_trips) == 0:
        return pd.Series(dtype=float)
    df = pd.DataFrame(round_trips)
    if "realised_pnl" not in df.columns:
        return pd.Series(dtype=float)
    if "position_id" not in df.columns or df["position_id"].isna().all():
        return df["realised_pnl"].astype(float).dropna()

    df = df.dropna(subset=["position_id"])
    if "closed_fully" in df.columns:
        closed_ids = df.loc[df["closed_fully"].astype(bool), "position_id"].unique()
        df = df[df["position_id"].isin(closed_ids)]
    if df.empty:
        return pd.Series(dtype=float)
    return df.groupby("position_id")["realised_pnl"].sum().astype(float)


def accuracy(round_trips) -> float:
    """Share of CLOSED POSITIONS that made money, net of costs on both legs.

    A position (open -> optional trims -> full exit) counts once, on its whole-life
    P&L - not once per trim. See _position_pnl."""
    pnl = _position_pnl(round_trips)
    if len(pnl) == 0:
        return float("nan")
    return float((pnl > 0).mean())


def accuracy_by_transaction(round_trips) -> float:
    """Share of individual closing transactions (trims + exits) that made money.

    Reported alongside `accuracy` for transparency: it counts every partial sell,
    so it is finer-grained and typically differs from the position-level number."""
    pnl = _transaction_pnl(round_trips)
    if len(pnl) == 0:
        return float("nan")
    return float((pnl > 0).mean())


def gain_to_loss_ratio(round_trips) -> float:
    """Mean winning P&L / mean absolute losing P&L, over closed POSITIONS."""
    pnl = _position_pnl(round_trips)
    if len(pnl) == 0:
        return float("nan")
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    if len(losses) == 0:
        return float("inf") if len(wins) else float("nan")
    if len(wins) == 0:
        return 0.0
    return float(wins.mean() / abs(losses.mean()))


def profit_factor(round_trips) -> float:
    """Gross profit / gross loss over closed POSITIONS - the aggregate cousin of
    gain-to-loss."""
    pnl = _position_pnl(round_trips)
    if len(pnl) == 0:
        return float("nan")
    gross_loss = abs(pnl[pnl < 0].sum())
    if gross_loss == 0:
        return float("inf") if pnl.sum() > 0 else float("nan")
    return float(pnl[pnl > 0].sum() / gross_loss)


def n_closed_positions(round_trips) -> int:
    """How many position episodes were fully closed - the true 'number of trades'."""
    return int(len(_position_pnl(round_trips)))


def trade_stats(trades, round_trips=None, nav: pd.Series = None) -> dict:
    """Execution-level statistics: counts, costs paid, and annualised turnover."""
    out = {
        "n_executions": 0,
        "n_buys": 0,
        "n_sells": 0,
        "n_closed_positions": 0,       # fully-closed position episodes = "trades"
        "n_closing_transactions": 0,   # every sell leg (trims + exits)
        "n_unique_stocks_traded": 0,
        "total_transaction_cost_inr": 0.0,
        "total_traded_notional_inr": 0.0,
        "annualised_turnover": float("nan"),
        "avg_trades_per_stock": float("nan"),
    }
    if trades is None or len(trades) == 0:
        return out

    df = pd.DataFrame(trades)
    out["n_executions"] = int(len(df))
    out["n_buys"] = int((df["side"] == "BUY").sum())
    out["n_sells"] = int((df["side"] == "SELL").sum())
    out["n_unique_stocks_traded"] = int(df["ticker"].nunique())
    out["total_transaction_cost_inr"] = float(df["cost"].sum())
    out["total_traded_notional_inr"] = float(df["notional"].sum())

    rt = pd.DataFrame(round_trips) if round_trips is not None and len(round_trips) else pd.DataFrame()
    out["n_closing_transactions"] = int(len(rt))
    out["n_closed_positions"] = n_closed_positions(round_trips)
    if out["n_unique_stocks_traded"]:
        # "Trades per stock" is reported over closed positions, the §7 sense of a trade.
        out["avg_trades_per_stock"] = round(
            out["n_closed_positions"] / out["n_unique_stocks_traded"], 3
        )

    if nav is not None and len(nav) > 1:
        nav = _clean_nav(nav)
        avg_nav = float(nav.mean())
        years = (len(nav) - 1) / TRADING_DAYS_PER_YEAR
        if avg_nav > 0 and years > 0:
            # Divide by 2: a full replacement of the book is one buy + one sell.
            out["annualised_turnover"] = float(
                out["total_traded_notional_inr"] / (2 * avg_nav) / years
            )
    return out


def all_metrics(
    nav: pd.Series,
    trades,
    risk_free_rate: float = 0.0,
    round_trips=None,
    starting_capital: float = None,
) -> dict:
    """Every metric the guidelines require, in one dict ready for metrics.json."""
    if round_trips is None:
        # Back-compat: if only one table is supplied, treat it as both.
        round_trips = trades

    return {
        "total_net_pnl_inr": total_net_pnl(nav, starting_capital),
        "total_return": total_return(nav),
        "annualised_return": annualised_return(nav),
        "annualised_volatility": annualised_volatility(nav),
        "max_drawdown": max_drawdown(nav),
        "max_drawdown_detail": max_drawdown_detail(nav),
        "sharpe_ratio": sharpe_ratio(nav, risk_free_rate),
        "sortino_ratio": sortino_ratio(nav, risk_free_rate),
        "calmar_ratio": calmar_ratio(nav),
        "gain_to_loss_ratio": gain_to_loss_ratio(round_trips),
        "profit_factor": profit_factor(round_trips),
        "accuracy": accuracy(round_trips),
        "accuracy_by_transaction": accuracy_by_transaction(round_trips),
        "trade_stats": trade_stats(trades, round_trips, nav),
        "starting_capital_inr": float(starting_capital) if starting_capital else float(pd.Series(nav).iloc[0]),
        "final_nav_inr": float(pd.Series(nav).dropna().iloc[-1]),
        "n_trading_days": int(len(pd.Series(nav).dropna())),
    }

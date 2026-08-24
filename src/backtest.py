"""
Event-driven portfolio accounting: apply the rebalance rule through time, track cash
and holdings and NAV, and charge transaction costs on every trade.

OWNER: Person B (engine/evaluation) - this is the module correctness matters most for.
A bug here silently invalidates every downstream metric.

THE THREE THINGS THAT MAKE THIS TRUSTWORTHY
1. Share-based accounting, not weight-based. We hold an integer number of shares and
   an explicit cash balance; NAV is derived from them. Weight-based accounting hides
   transaction costs and cannot represent cash drag honestly.
2. Signal and execution are separated by one trading day. Scores are computed from
   prices up to and including day d, and the resulting trades execute at day d+1's
   close. Scoring and trading on the same close would mean acting on a price that had
   not been observable when the decision was made - the classic look-ahead bug.
3. Costs are charged on notional, on BOTH legs. A buy costs `notional * cost_pct` and
   so does a sell; the cost is added to the buy cost basis and deducted from the sell
   proceeds, so it flows into realised P&L rather than being accounted separately.

WHAT COUNTS AS A "TRADE"
The guidelines ask for accuracy and gain-to-loss, which are only defined over closed
positions. We therefore report two tables:
  `trades`       every execution (one row per buy or sell leg).
  `round_trips`  one row per position CLOSED, with realised P&L measured against the
                 average cost of the shares sold, net of costs on both legs.
Accuracy and gain-to-loss are computed over `round_trips`. Positions still open on the
final day are returned separately in `open_positions` and are NOT counted as trades -
counting an open winner as a "profitable trade" would inflate accuracy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.factors import low_vol_score, score_universe


def get_rebalance_dates(index: pd.DatetimeIndex, frequency: str = "M") -> list:
    """First trading day of each period in `index`.

    Trading on the first day of the month (rather than the last) means the decision
    uses a complete prior month of data and is not entangled with month-end index
    rebalancing flows.
    """
    freq = (frequency or "M").upper()
    if freq in ("M", "MONTHLY"):
        period = "M"
    elif freq in ("Q", "QUARTERLY"):
        period = "Q"
    elif freq in ("W", "WEEKLY"):
        period = "W"
    elif freq in ("A", "Y", "ANNUAL", "YEARLY"):
        period = "Y"
    else:
        raise ValueError("unsupported rebalance frequency %r" % frequency)

    s = pd.Series(index, index=index)
    return list(s.groupby(index.to_period(period)).first().values)


def _portfolio_value(shares: dict, prices_row: pd.Series, last_known: dict) -> float:
    """Mark holdings to market, falling back to the last observed price on a NaN."""
    total = 0.0
    for ticker, n in shares.items():
        if n == 0:
            continue
        px = prices_row.get(ticker, np.nan)
        if pd.isna(px):
            px = last_known.get(ticker, np.nan)
        if pd.isna(px):
            continue
        total += n * float(px)
    return total


def run_backtest(
    prices: pd.DataFrame,
    universe: pd.DataFrame,
    config: dict,
    volumes=None,
    history: pd.DataFrame = None,
    volume_history: pd.DataFrame = None,
) -> dict:
    """Run the strategy over `prices` and return NAV, trades and diagnostics.

    Parameters
    ----------
    prices : wide DataFrame (dates x tickers) of adjusted closes for the RUN WINDOW.
    universe : output of universe.load_universe(); restricts the tradeable columns.
    config : parsed config.yaml.
    volumes : matching volume panel for the run window (liquidity filter).
    history : prices BEFORE the run window. Factors need ~12 months of lookback, so
        without this the first year of any run would be unscoreable. This is warm-up
        data only - it is never traded on and never contributes to NAV.
    volume_history : matching volume warm-up panel.

    Returns
    -------
    dict with keys: nav, trades, round_trips, weights_history, open_positions.
    """
    if prices.empty:
        raise ValueError("run_backtest received an empty price panel")

    cost_pct = float(config["costs"]["transaction_cost_pct"])
    starting_capital = float(config["capital"]["starting_value_inr"])
    max_holdings = int(config["universe"]["max_holdings"])
    scheme = config["rebalance"]["weighting_scheme"]
    max_weight = float(config["rebalance"]["max_weight_per_stock"])
    buffer_rank = config["rebalance"].get("buffer_rank")

    from src.portfolio import select_stocks, weight_stocks

    # Only trade names that are in the universe AND present in the price panel.
    tradeable = [t for t in universe["ticker"].unique() if t in prices.columns]
    benchmark_ticker = config["benchmark"]["ticker"]
    tradeable = [t for t in tradeable if t != benchmark_ticker]
    if not tradeable:
        raise ValueError("no universe tickers found in the price panel")

    px = prices[tradeable]
    vol_panel = (
        volumes[tradeable].reindex(index=px.index)
        if volumes is not None
        else pd.DataFrame(1e18, index=px.index, columns=tradeable)
    )

    # Glue warm-up history in front so factors are computable on day one.
    if history is not None and not history.empty:
        hist_cols = [t for t in tradeable if t in history.columns]
        hist = history[hist_cols].reindex(columns=tradeable)
        hist = hist.loc[hist.index < px.index.min()]
        scoring_px = pd.concat([hist, px])
        if volume_history is not None and not volume_history.empty:
            vh = volume_history.reindex(columns=tradeable)
            vh = vh.loc[vh.index < px.index.min()]
            scoring_vol = pd.concat([vh, vol_panel])
        else:
            scoring_vol = vol_panel.reindex(index=scoring_px.index)
    else:
        scoring_px = px
        scoring_vol = vol_panel

    rebalance_dates = set(pd.Timestamp(d) for d in get_rebalance_dates(px.index, config["rebalance"]["frequency"]))

    cash = starting_capital
    shares: dict = {}
    avg_cost: dict = {}          # cost basis per share, inclusive of the buy-side cost
    last_known: dict = {}
    pending_target = None        # weights decided yesterday, executed today

    nav_records = []
    trade_records = []
    round_trips = []
    weight_records = []

    dates = list(px.index)
    for i, date in enumerate(dates):
        row = px.loc[date]
        for t in row.index:
            v = row[t]
            if not pd.isna(v):
                last_known[t] = float(v)

        # ---- 1. Execute whatever was decided at the previous close ----------
        if pending_target is not None:
            nav_before = cash + _portfolio_value(shares, row, last_known)
            target_w = pending_target
            pending_target = None

            # Target rupee exposure per name, then convert to whole shares.
            target_shares = {}
            for ticker, w in target_w.items():
                price = row.get(ticker, np.nan)
                if pd.isna(price) or price <= 0:
                    # Cannot trade a name with no price today; keep the existing
                    # position rather than forcing a fill at a made-up price.
                    target_shares[ticker] = shares.get(ticker, 0)
                    continue
                target_shares[ticker] = int(np.floor((w * nav_before) / float(price)))

            # Anything held but not in the target is a full exit.
            for ticker in list(shares):
                if ticker not in target_shares:
                    target_shares[ticker] = 0

            # Sells first, so their proceeds fund the buys.
            for ticker in sorted(target_shares, key=lambda t: target_shares[t] - shares.get(t, 0)):
                held = shares.get(ticker, 0)
                want = target_shares[ticker]
                delta = want - held
                if delta == 0:
                    continue
                price = row.get(ticker, np.nan)
                if pd.isna(price) or price <= 0:
                    continue
                price = float(price)
                notional = abs(delta) * price
                cost = notional * cost_pct

                if delta < 0:  # SELL
                    n_sold = -delta
                    proceeds = notional - cost
                    basis = avg_cost.get(ticker, price) * n_sold
                    realised = proceeds - basis
                    cash += proceeds
                    shares[ticker] = held + delta
                    round_trips.append(
                        {
                            "exit_date": date,
                            "ticker": ticker,
                            "shares": n_sold,
                            "avg_cost": avg_cost.get(ticker, price),
                            "exit_price": price,
                            "gross_proceeds": notional,
                            "exit_cost": cost,
                            "realised_pnl": realised,
                            "return_pct": realised / basis if basis > 0 else np.nan,
                            "closed_fully": shares[ticker] == 0,
                        }
                    )
                    if shares[ticker] == 0:
                        shares.pop(ticker, None)
                        avg_cost.pop(ticker, None)
                else:  # BUY
                    outlay = notional + cost
                    if outlay > cash:
                        # Never let the book go overdrawn - trim to affordable size.
                        affordable = int(np.floor(cash / (price * (1 + cost_pct))))
                        if affordable <= 0:
                            continue
                        delta = affordable
                        notional = delta * price
                        cost = notional * cost_pct
                        outlay = notional + cost
                    prev_shares = held
                    prev_basis = avg_cost.get(ticker, 0.0) * prev_shares
                    new_shares = prev_shares + delta
                    avg_cost[ticker] = (prev_basis + notional + cost) / new_shares
                    shares[ticker] = new_shares
                    cash -= outlay

                trade_records.append(
                    {
                        "date": date,
                        "ticker": ticker,
                        "side": "SELL" if delta < 0 else "BUY",
                        "shares": abs(delta),
                        "price": price,
                        "notional": notional,
                        "cost": cost,
                    }
                )

        # ---- 2. Mark to market ---------------------------------------------
        holdings_value = _portfolio_value(shares, row, last_known)
        nav = cash + holdings_value
        nav_records.append({"date": date, "nav": nav, "cash": cash, "holdings_value": holdings_value})

        if shares:
            weight_records.append(
                {
                    "date": date,
                    **{
                        t: (n * last_known.get(t, 0.0)) / nav if nav > 0 else 0.0
                        for t, n in shares.items()
                    },
                }
            )

        # ---- 3. Decide tomorrow's book -------------------------------------
        # Skip the final day: there is no next session to execute in.
        if date in rebalance_dates and i < len(dates) - 1:
            hist_slice = scoring_px.loc[:date]
            vol_slice = scoring_vol.loc[:date]
            scores = score_universe(hist_slice, vol_slice, config)
            selected = select_stocks(
                scores,
                max_holdings=max_holdings,
                current_holdings=set(shares),
                buffer_rank=buffer_rank,
            )
            if selected:
                vols = None
                if scheme == "inverse_vol":
                    vols = -low_vol_score(
                        hist_slice[selected],
                        lookback_months=config.get("factors", {}).get("low_vol_lookback_months", 6),
                    )
                pending_target = weight_stocks(
                    selected,
                    scores,
                    scheme=scheme,
                    max_weight_per_stock=max_weight,
                    volatilities=vols,
                )

    nav_df = pd.DataFrame(nav_records).set_index("date")
    nav_series = nav_df["nav"].astype(float)

    final_row = px.loc[dates[-1]]
    open_positions = pd.DataFrame(
        [
            {
                "ticker": t,
                "shares": n,
                "avg_cost": avg_cost.get(t, np.nan),
                "last_price": last_known.get(t, np.nan),
                "market_value": n * last_known.get(t, np.nan),
                "unrealised_pnl": n * (last_known.get(t, np.nan) - avg_cost.get(t, np.nan)),
            }
            for t, n in shares.items()
        ]
    )

    return {
        "nav": nav_series,
        "cash": nav_df["cash"].astype(float),
        "trades": pd.DataFrame(trade_records),
        "round_trips": pd.DataFrame(round_trips),
        "weights_history": pd.DataFrame(weight_records).set_index("date")
        if weight_records
        else pd.DataFrame(),
        "open_positions": open_positions,
        "final_nav": float(nav_series.iloc[-1]),
        "starting_capital": starting_capital,
    }

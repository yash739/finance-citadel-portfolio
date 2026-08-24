# Strategy notes

Plain-language source of truth for the methodology. This is most of what turns
directly into the report's "Methodology" and "Limitations" sections.

All parameters live in `config.yaml`. Nothing below is hardcoded in `src/`.

---

## Stock-selection rule

Rank the eligible universe by an **equally-weighted composite of two price-only
factors**, and take the top 10:

- **12-1 momentum** — cumulative return over the trailing 12 months, *excluding* the
  most recent month. The skip is not cosmetic: the last month is contaminated by
  short-term reversal, and including it measurably degrades the factor.
- **Low volatility** — negative annualised standard deviation of daily returns over
  the trailing 6 months. Lower realised vol scores higher.

Both factors are z-scored cross-sectionally on each rebalance date, then combined
0.5 / 0.5. Z-scoring first is what makes the weights meaningful — raw momentum is a
return (order 0.1–1.0) while raw low-vol is a negative volatility (order −0.2 to
−0.8), so a naive weighted sum would be dominated by scale rather than by the weight
we chose.

A stock is scored only if it has a value for **every** factor. Partial scoring would
quietly advantage names that happen to be missing their weakest factor.

**Liquidity screen, applied before ranking:** average daily rupee turnover
(close × volume) over the trailing 3 months must exceed ₹5 crore. At ₹1 crore of
capital and ≤10 names, a position is ₹10–25 lakh, comfortably under 1% of a typical
day's volume — so the fills we assume are realistic. Without this screen the model
will happily "select" a smallcap that could not absorb the position.

## Weighting rule

Rank-proportional among the selected names, capped at 25% per stock, renormalised
after capping (iteratively — redistributing excess can push another name over the cap).

**Why rank-proportional and not literally score-proportional:** the composite is a
z-score, so it is signed and centred on zero. Weight-proportional-to-score is
undefined when a score is negative (negative weights would mean short positions,
which this long-only mandate forbids) and explodes when a score is near zero. Ranks
are monotone in score, always positive, and scale-free. The alternative — shifting all
scores positive by subtracting the minimum — makes every weight depend on whichever
single worst name happens to be in the book that month.

If the cap makes full investment impossible (fewer than 4 names), the book stays
partially in cash rather than breaching the risk limit.

## Rebalancing rule

Monthly, on the **first trading day of the month**. Trading at the start rather than
the end means the decision uses a complete prior month of data and is not entangled
with month-end index-rebalancing flows.

**Signal and execution are separated by one trading day.** Scores are computed from
prices up to and including day *d*; the resulting trades execute at day *d+1*'s close.
Scoring and trading on the same close would mean acting on a price that was not
observable when the decision was made.

**Hysteresis:** a name already held is only sold once it drops out of the top 15
(`buffer_rank`). New entrants must still crack the top 10. Without this, a stock
oscillating around rank 10 is sold and rebought every month, paying 0.1% each way for
no change in exposure. This is a turnover-reduction rule, not a return-seeking one,
and it is applied identically in both run windows.

## Risk management

- ≤10 holdings at all times (mandate).
- 25% maximum weight per stock, enforced at every rebalance.
- Liquidity screen (above).
- Long-only, cash-funded: no leverage, no shorts, cash never goes negative.

## Why this is expected to generalise out-of-sample

*(Written before looking at the out-of-sample result.)*

Momentum and low-volatility are two of the most heavily documented factors in the
literature, across decades and across markets. The rule has two free parameters (the
lookback windows), both set from convention — 12-1 and 6 months — rather than
optimised on this data. The factor weights are a flat 0.5 / 0.5, not fitted. There are
no stock-specific overrides and no re-fitting between the in-sample and out-of-sample
runs: `run_backtest.py` executes the identical rule over both windows.

---

## What the results actually showed

Numbers from `reports/metrics_*.json`, regenerate with `python run_backtest.py`.

| | In-sample 2021–2025 | Out-of-sample 2026 H1 |
|---|---|---|
| Total Net PNL | ₹6.40 Cr | ₹3,067 |
| Total return | 640.5% | 0.03% |
| CAGR | 50.5% | 0.06% |
| Sharpe | 2.12 | 0.00 |
| Max drawdown | −24.9% | −17.9% |
| Accuracy | 72.3% | 36.8% |
| Gain-to-loss | 1.01 | 0.62 |
| Nifty 100 over same window | +89.4% | −6.4% |

**The in-sample number is substantially an artifact, and the report must say so.**

`python -m src.diagnostics` measures this directly. Equal-weight buy-and-hold across
the entire 300-name snapshot universe — no factors, no selection, zero skill — returns
**34.4% CAGR in-sample** against the Nifty 100's 13.9%. A skill-free portfolio cannot
generate alpha, so that ~20 pp/yr gap is the size of the survivorship distortion.

That gives a clean three-way decomposition of the headline result:

| Component | In-sample | Out-of-sample |
|---|---|---|
| Excess over Nifty 100 | +36.5 pp/yr | +13.0 pp/yr |
| …attributable to survivorship bias | **+20.5 pp/yr** | **+16.7 pp/yr** |
| …attributable to factor selection | +16.0 pp/yr | **−3.7 pp/yr** |

**Out-of-sample, the strategy underperforms an equal-weight hold of its own
universe.** The factor model subtracted 3.7 pp/yr there. In-sample it added 16.0 pp/yr.
That gap between the two windows is the honest headline finding, and pretending the
640% is strategy performance would not survive five minutes of questioning.

Because of this, `run_backtest.py` reports an **equal-weight-own-universe benchmark**
alongside the Nifty 100. It carries the identical survivorship bias on both sides of
the comparison, so it isolates what the factor model actually contributed. It is the
fair benchmark; the Nifty 100 comparison flatters the strategy by roughly 20 pp/yr.

## Known limitations / assumptions to disclose in the report

- **Survivorship and look-ahead bias — the big one.** Universe membership is a single
  snapshot of index constituents taken 2026-08-25 and applied retroactively to
  2021–2025. Index promotion follows good performance, so the 2026 Smallcap 100 is by
  construction a list of stocks that went up. Quantified above at roughly +20 pp/yr
  in-sample. Free point-in-time constituent data does not exist for these indices;
  this is a disclosed simplification, not a bug.
- **The out-of-sample window is short** (122 trading days, 38 closed round trips).
  Metrics computed on 38 trades carry very wide error bars — the 36.8% accuracy is not
  meaningfully distinguishable from the in-sample 72.3% at this sample size. Do not
  over-read either number.
- **Execution is modelled as a fill at the close** with a flat 0.1% cost. Real costs
  include bid-ask spread, market impact and STT/stamp duty, which the 0.1% figure may
  not fully cover for the smaller names, even after the liquidity screen.
- **Whole-share trading**, with the residual left in cash. Minor, but it means the book
  is never exactly 100% invested.
- **No fundamental or value factor** — price-only by design, given the data-sourcing
  constraints on this timeline.
- **yfinance data quality** for illiquid smallcap names is not independently verified
  against a paid vendor. All 300 tickers downloaded cleanly with 0 failures and no name
  above 5% missing days (see `data/processed/data_quality.csv`), but 64 of them listed
  after the backtest start and are simply unscoreable until they have 12 months of
  history.
- **"Trade" is defined as a closed round trip** — a sell that closes some or all of a
  position, with P&L measured against average cost, net of costs on both legs.
  Positions still open on the final day are reported separately and are NOT counted as
  trades; counting an open winner as a profitable trade would inflate accuracy.

## Open decisions

- Whether to submit the strategy as-is with the bias disclosed, or to switch the
  headline comparison to the bias-matched benchmark. Recommend the latter — it is the
  defensible number and the decomposition is a genuinely strong report section.
- Whether to attempt a point-in-time universe reconstruction from historical index
  factsheets. High effort; would remove the largest caveat.

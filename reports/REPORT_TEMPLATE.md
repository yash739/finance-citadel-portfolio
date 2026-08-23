# Finesse x Citadel — Round 2 Report

> **Team:** _______________  **Members:** _______________  **Date:** _______________
>
> Target length **5–6 pages** (guidelines §9). Section headings below follow the
> suggested structure; the guidelines allow a different structure *as long as every
> element here is covered*. Delete this block and all _italic guidance_ before submitting.
>
> Suggested page budget: §1 ~0.75p · §2 ~1p · §3 ~1.5p · §4 ~0.25p · §5 ~1.25p · §6 ~0.75p · §7 ~0.5p

---

## 1. Problem and Strategy Overview

_State the mandate in two lines: ≤10 stocks, Nifty 100 / Midcap 100 / Smallcap 100
universe, ₹1 crore starting capital, 1 Jan 2021 – 31 Dec 2025._

_Then the central idea of the strategy in plain language — the one-paragraph version a
juror could repeat back. What inefficiency or premium are you harvesting, and why should
it persist? The guidelines' key principle is "build a strategy you can explain and
defend," and §6 warns that hindsight-heavy models will not survive the out-of-sample
window. Lead with the rationale, not the returns._

**Strategy in one sentence:** _______________

## 2. Data

_Cover each of these — §9 names them explicitly:_

| Item | Detail |
|---|---|
| Source | _e.g. yfinance, NSE tickers with `.NS` suffix_ |
| Frequency | _daily OHLCV_ |
| Period pulled | _incl. lookback before 2021-01-01 so factors are computable on day 1_ |
| Variables / features | _adjusted close, volume, returns, ..._ |
| Universe source | _index constituent lists; state the as-of date_ |
| Cleaning / preprocessing | _split & dividend adjustment, missing-data handling, illiquidity filters_ |

_Be specific about two things evaluators will look for:_
- _**Adjusted vs raw close** — which you used and how splits/dividends are handled._
- _**Survivorship / look-ahead bias** — using *today's* constituent list across 2021–2025
  means past-you could not have known the membership. Disclose it here or in §7; do not
  let an evaluator discover it themselves._

## 3. Methodology

_The heart of the report. §3 of the guidelines asks for four things by name:_

### 3.1 Stock-selection rule
_What signals drive entry, how they are computed, how they combine into a score, and how
the top ≤10 are chosen. State the exact ranking rule._

### 3.2 Weighting rule
_Equal, score-proportional, inverse-volatility, or an optimisation. State the concentration
cap and what happens when it binds (renormalise how?)._

### 3.3 Rebalancing / trading logic
_Frequency and the exact trigger. When is the portfolio reviewed, what forces a trade, and
any hysteresis/buffer rule used to suppress churn. Confirm the 0.1% cost is charged on
**every buy and every sell**, on notional traded._

### 3.4 Risk management
_Position caps, sector/cap-segment limits, cash rules, drawdown controls — or state
explicitly that there are none beyond the weight cap, which is a defensible choice if owned._

> **Consistency check (§3):** the same core methodology must apply to every holding. If any
> rule was applied stock-by-stock to improve backtest results, either remove it or justify it.

## 4. Tools / Software Used

_Language, libraries, and any statistical / optimisation / ML tooling. Keep it to a short
list — this section is a quarter page. Point to `requirements.txt` for exact versions._

## 5. Results and Performance Metrics

### 5.1 Final portfolio composition

| Ticker | Name | Sector | Index | Weight |
|---|---|---|---|---|
| | | | | |

### 5.2 Required metrics

_Every row below is mandatory under §7. Blank cells will read as missing work._

| Metric | Definition used | Backtest 2021–2025 | OOS 2026 H1 |
|---|---|---|---|
| Total Net PNL | Final value − ₹1,00,00,000 | | |
| Absolute / total return | | | |
| Annualised return | Geometric (CAGR) | | |
| Maximum Drawdown | Largest peak-to-trough | | |
| Sharpe Ratio | Ann. return ÷ σ(daily returns), **rf = 0%** | | |
| Gain-to-Loss Ratio | Avg profit on winners ÷ avg loss on losers | | |
| Accuracy | % of trades profitable | | |
| Total trades | | | |
| Trades per stock | | | |
| Turnover | | | |
| Total transaction costs paid | | | |

> **Total Net PNL is the primary ranking metric (§5).** Lead §5 with it, in rupees.
>
> State your trade-level conventions once, here: a "trade" is a round-trip (buy→sell) vs a
> single fill, and partial rebalances are counted as _____. Accuracy and gain-to-loss are
> not comparable across teams without this, and evaluators cannot reproduce your numbers
> from `reports/metrics.json` if the definition is implicit.

### 5.3 Figures
_Equity curve vs benchmark; drawdown curve. Both must be readable in greyscale print._

## 6. Benchmark Comparison

_§8 requires you to **name the benchmark and justify it**. Nifty 100 or Nifty 500 are the
suggested options — pick the one whose cap profile actually matches where your holdings
land, and say so. If your portfolio skews midcap/smallcap, a Nifty 100 benchmark flatters
you and a juror will notice._

| | Portfolio | Benchmark | Difference |
|---|---|---|---|
| Total return | | | |
| Annualised return | | | |
| Maximum Drawdown | | | |
| Sharpe | | | |

_Discuss both **relative performance** and **risk-adjusted** over/underperformance — not
just the return gap. If you underperformed on return but with materially lower drawdown,
make that argument explicitly._

## 7. Limitations / Discussion

_§9 asks for limitations and "situations in which the strategy may not perform as expected."
Candour scores better than a clean sheet — the jury round rewards robustness and
transparency. Cover at least:_

- _Survivorship / look-ahead from static constituent lists_
- _Liquidity and impact assumptions — 0.1% cost only models explicit cost, not slippage;
  flag if any smallcap holding is large relative to typical traded volume_
- _Regime dependence — what market conditions break this strategy_
- _Parameter sensitivity — how much results move if lookbacks / thresholds shift_
- _Any deviation between the backtest and how this would trade live_

---

## Pre-submission checklist (guidelines §11)

- [ ] Only Nifty 100 / Midcap 100 / Smallcap 100 stocks used
- [ ] ≤10 holdings at all times
- [ ] Backtest covers 1 Jan 2021 – 31 Dec 2025
- [ ] Starting capital ₹1,00,00,000
- [ ] 0.1% transaction cost applied on every buy and sell
- [ ] Selection + weighting methodology explained and consistently applied
- [ ] All §7 metrics reported **and** reproducible from the code
- [ ] Benchmark named, justified, and discussed
- [ ] Repo has complete code and a clear README
- [ ] Report is ~5–6 pages and covers data, methodology, tools, results, benchmark, limitations
- [ ] Out-of-sample run uses the identical rule — no refitting
- [ ] **Submitted by 31 August**

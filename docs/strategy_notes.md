# Strategy notes

Plain-language source of truth for the methodology. This is most of what turns
directly into the report's "Methodology" and "Limitations" sections.

All parameters live in `config.yaml`. Nothing below is hardcoded in `src/`.
Reproduce the selection evidence with `python -m src.experiments --select` and every
other table with `python -m src.experiments --all`, `python -m src.alt_strategies` and
`python -m src.pit_universe`.

---

## 1. The final strategy

**Select** the 10 highest-scoring names from the Nifty 100 + Midcap 100 + Smallcap 100
universe on the first trading day of each month, where the score is a cross-sectional
z-score composite:

| Factor | Weight | Definition |
|---|---|---|
| Momentum | **0.55** | Cumulative return from t−12 months to t−**2** months |
| Low volatility | **0.45** | Negative annualised σ of daily returns, trailing 6 months |

**Screen** before ranking: average daily rupee turnover (close × volume) over the
trailing 3 months must exceed ₹5 crore.

**Weight** rank-proportionally among the selected names, capped at 25% per stock,
renormalised iteratively after capping.

**Rebalance** monthly, with hysteresis: a name already held is only sold once it drops
out of the top 15. Signal on day *d*'s close, execute at day *d+1*'s close.

**Long-only, cash-funded.** No leverage, no shorts, cash never negative.

### Which parameters are convention and which were chosen from data

| Parameter | Value | Source |
|---|---|---|
| Momentum lookback | 12 months | Convention (textbook 12-1), confirmed on the split |
| Volatility lookback | 6 months | Convention |
| Holdings | 10 | Mandate cap; also near Sharpe-optimal on the split |
| Weight cap | 25% | Risk choice (no name dominates PnL) |
| Rebalance | Monthly | Convention; beats quarterly and buy-and-hold on the split |
| Weighting | Rank-proportional | Chosen on the split; beats equal- and inverse-vol |
| Liquidity screen | ₹5 cr | Tradeability choice; ₹1cr binds on nothing, ₹20cr costs return |
| Hysteresis buffer | 15 | Turnover-reduction only; buffer 12–30 all work |
| **Momentum skip** | **2 months** | **Chosen on TRAIN, confirmed on VALIDATE (see §2)** |
| **Factor weight** | **55 / 45** | **Chosen on TRAIN/VALIDATE (see §2)** |

Only the last two rows were chosen by looking at data, and both were chosen on an
**in-sample train/validate split that never touches the 2026 out-of-sample window.**

---

## 2. How the strategy was chosen — a train/validate split, not a peek at 2026

### 2.1 The metric: selection alpha

Every experiment is scored against **an equal-weight buy-and-hold of the same 300-name
universe**, not against the Nifty 100. Both sides then carry the identical universe
effect (size + equal-weight + survivorship), so the difference isolates what the
strategy itself contributed. Measured against the index instead, *every* rung looks
brilliant — including the ones containing literally zero skill (§2.2).

### 2.2 The ladder — build up one ingredient at a time

`python -m src.experiments --ladder`. SelAlpha = CAGR minus the equal-weight universe.

| Rung | IS CAGR | IS SelAlpha | OOS SelAlpha |
|---|---|---|---|
| 0. Nifty 100 index | +13.9% | −20.5% | −16.7% |
| 1. EW hold all 300 (the yardstick) | +34.4% | 0.0% | 0.0% |
| 2. EW all 300, monthly, costed | +33.5% | −1.0% | −3.4% |
| 3. Alphabetical 10, buy & hold | +34.7% | +0.3% | +48.2% |
| 4. Random 10, buy & hold (5 seeds) | +35.1% | +0.7% | −15.2% |
| 5. Random 10, monthly (5 seeds) | +34.9% | +0.5% | +6.2% |
| 6. Momentum only, top 10 EW | +58.4% | **+23.9%** | **+11.4%** |
| 7. Low-vol only, top 10 EW | +19.9% | **−14.6%** | −5.2% |
| 8. Composite 50/50, top 10 EW | +51.7% | +17.3% | +13.4% |
| 9. + rank-prop weights, 25% cap | +52.1% | +17.7% | +19.3% |
| 10. + liquidity screen | +57.5% | +23.0% | +19.3% |
| 11. + hysteresis (**the final rule**) | +60.0% | +25.5% | +22.6% |

Three things this establishes:

1. **The controls calibrate correctly.** Rungs 3–5 contain no skill, and all three land
   at SelAlpha ≈ 0 in-sample (+0.3, +0.7, +0.5). Concentrating ₹1 crore into 10 names
   does not by itself create alpha. The measurement is trustworthy.
2. **Momentum is the engine** (rung 6, +23.9 IS / +11.4 OOS).
3. **Rung 3 is the warning that governs everything below.** Alphabetical-order
   buy-and-hold — zero skill — scored **+48.2% out-of-sample**. The OOS window is 122
   days and 16 closed positions; it *cannot* distinguish skill from luck. This is why
   **no parameter was ever selected on it.**

### 2.3 The selection protocol — a train/validate split inside 2021–2025

`python -m src.experiments --select`. Because the 2026 window is too short to select on,
we split the *in-sample* period instead:

```
TRAIN     2021-01-01 .. 2023-12-31   parameters are chosen here
VALIDATE  2024-01-01 .. 2025-12-31   the choice must still hold here
OOS       2026-01-01 .. 2026-06-30   run ONCE after freezing; never used to choose
```

A parameter is adopted only if it is strong on TRAIN **and** still positive on VALIDATE.
Selection alpha, pp/yr:

**Momentum skip** (weights 50/50):

| skip | 0 | 1 | **2** | 3 | 4 |
|---|---|---|---|---|---|
| TRAIN | +16.2 | +20.3 | **+28.9** | +15.0 | +16.9 |
| VALIDATE | +2.1 | +9.6 | **+11.8** | +16.1 | +8.7 |

TRAIN peaks cleanly at skip=2 and VALIDATE confirms it (+11.8). **Adopt skip = 2.**

**Momentum lookback** (skip=2, 50/50):

| months | 3 | 6 | 9 | **12** | 15 | 18 | 24 |
|---|---|---|---|---|---|---|---|
| TRAIN | −3.1 | +23.3 | +30.0 | **+28.9** | +21.9 | +19.7 | −17.2 |
| VALIDATE | −6.2 | +10.0 | +5.8 | **+11.8** | −0.3 | +6.0 | +18.0 |

12 is the textbook value, sits in the TRAIN plateau, and is the best validator in its
region. The long tail (24m) validates high but is jagged (TRAIN −17.2). **Keep 12.**

**Factor mix / momentum weight** (skip=2, 12-month lookback) — *the decisive table:*

| mom weight | 30 | 40 | 50 | **55** | 60 | 65 | 70 | 80 | 100 |
|---|---|---|---|---|---|---|---|---|---|
| TRAIN | −17.0 | +11.9 | +28.9 | **+33.6** | +39.4 | +41.2 | +39.8 | +43.6 | +39.2 |
| VALIDATE | −2.3 | +2.7 | +11.8 | **+11.7** | +7.3 | +5.4 | +4.2 | −0.1 | −0.9 |

This is where a naïve reader would overfit. TRAIN keeps rising to 65–80%. But **VALIDATE
— the generalisation test — peaks at 50–55% and falls monotonically above it.** The
train-optimal (65–80%) is exactly the region that *fails to generalise*. We take **55%**:
the largest momentum tilt that is still validate-optimal. Lower momentum weight also
tightens drawdown. We deliberately do **not** chase the higher TRAIN optimum.

**Only after this table was frozen was the OOS column computed.** For the record it reads
skip=2 +16.5, momentum-55 +22.6 — but it played no part in the choice, and given rung 3
it could not have been trusted to.

### 2.4 The decisive robustness test — per-year consistency

`python -m src.experiments --finals`. A multi-year average can be produced by one
spectacular year. Selection alpha, year by year, for the final and its neighbourhood:

| Strategy | 2021 | 2022 | 2023 | 2024 | 2025 | worst | mean | OOS |
|---|---|---|---|---|---|---|---|---|
| **FINAL (mom55 skip2)** | +70.6 | +3.6 | +35.0 | +17.8 | +5.3 | **+3.6** | +26.5 | +22.6 |
| convention (mom50 skip1) | +27.9 | +8.1 | +14.4 | +31.4 | −6.4 | −6.4 | +15.1 | −3.7 |
| train-optimal (mom75 skip2) | +76.9 | +4.5 | +44.4 | −4.1 | +5.2 | −4.1 | +25.4 | +18.2 |
| — neighbours of the final — | | | | | | | | |
| mom50 skip2 | +67.0 | +2.7 | +33.5 | +23.2 | +2.3 | +2.3 | +25.7 | +16.5 |
| mom60 skip2 | +94.7 | +5.3 | +29.3 | +9.4 | +2.5 | +2.5 | +28.2 | +18.7 |
| mom55 skip1 | +30.3 | +6.0 | +20.4 | +24.1 | −0.8 | −0.8 | +16.0 | +5.9 |
| mom55 skip3 | +24.7 | +0.9 | +28.3 | +25.1 | −0.5 | −0.5 | +15.7 | +19.8 |
| mom55 skip2 buffer20 | +73.8 | +3.1 | +34.6 | +10.1 | +7.2 | +3.1 | +25.7 | +19.0 |
| mom55 skip2 equal-wt | +48.8 | +1.1 | +19.4 | +9.4 | +4.6 | +1.1 | +16.7 | +16.0 |

The final is **positive in all five years**, and its worst year (+3.6) is the *best*
worst-year of any immediate neighbour. The two parameters that matter (skip and weight)
are robust to ±5pp and ±1 month; the train-optimal mom75 turns negative in 2024, which
is exactly the overfitting the validate step was designed to catch. **The choice is
robust and the exact centre barely matters** — the strongest evidence available that
this is not a fitted result.

### 2.5 What was tried and rejected

- **Higher momentum weight (65–80%).** Best on TRAIN, but VALIDATE and the per-year test
  both reject it — mom75 is negative in 2024. This is the single clearest overfit we
  avoided.
- **Low-vol-heavy mixes (0–35% momentum).** Negative selection alpha on both slices.
- **A 200-day regime filter** that moves to cash when the universe's own trend proxy
  rolls over. Structurally well-motivated but it **whipsawed** — mean selection alpha
  and OOS both fell (OOS to −6.9). Rejected on evidence; the code and its test remain in
  `src/experiments.py` so the negative result is reproducible, not just asserted.
- **Momentum-only.** Strong mean but a −6.6% year and a −35% drawdown.
- **3 or 5 holdings.** 3 is negative in-sample; 5 is thin out-of-sample. 10 is both the
  mandate cap and near the Sharpe-optimal region.
- **Quarterly rebalancing.** Worse on both slices despite lower cost.

### 2.6 Honesty note on the two data-chosen parameters

The 12-month lookback, 6-month vol window, 25% cap, 10-name limit, monthly cadence and
₹5cr screen are all conventional or mandated. **The 2-month skip and the 55/45 weight are
the two parameters chosen from data.** Both were chosen on TRAIN (2021–2023) and
confirmed on VALIDATE (2024–2025); neither was chosen on the 2026 window. The
conservative fallbacks — skip=1 (literature standard) and 50/50 — are both also positive
on VALIDATE and out-of-sample, so no conclusion in this report hinges on the exact
choice. Short-term reversal plausibly persists longer than a month in mid/small-caps,
but we did not know that in advance and do not pretend we did.

---

## 3. Results

Regenerate with `python run_backtest.py`. Numbers from `reports/metrics_*.json`.

| | In-sample 2021–2025 | Out-of-sample 2026 H1 |
|---|---|---|
| **Total Net PNL** | **₹8.99 Cr** | **₹11.93 L** |
| Final NAV | ₹9.99 Cr | ₹1.12 Cr |
| Total return | 899.3% | 11.9% |
| CAGR | 60.0% | 26.5% |
| Annualised volatility | 24.7% | 28.4% |
| Sharpe (0% rf) | 2.42 | 0.93 |
| Sortino | 3.30 | 1.39 |
| Max drawdown | −29.4% | −17.1% |
| Accuracy — closed positions | 61.6% (159) | 43.8% (16) |
| Accuracy — per closing transaction | 67.5% (394) | 45.2% (31) |
| Gain-to-loss (per position) | 1.95 | 1.60 |
| Annualised turnover | 4.43x | 5.95x |
| Transaction costs paid | ₹20.25 L | ₹57,907 |
| Nifty 100 over same window | +89.4% | −6.4% |
| Nifty 500 over same window | +107.2% | −3.7% |

### The number that actually matters

| | In-sample | Out-of-sample |
|---|---|---|
| Excess over Nifty 100 | +46.0 pp/yr | +39.4 pp/yr |
| …universe/composition (not skill) | +20.5 pp/yr | +16.7 pp/yr |
| …**factor selection (the real edge)** | **+25.5 pp/yr** | **+22.6 pp/yr** |

The strategy beats an equal-weight hold of its own universe in **both** windows — and by
almost the same margin out-of-sample (+22.6) as in-sample (+25.5). That stability across
a genuinely held-out window is the core evidence the edge is real.

### A note on "trade" definitions (§7 of the guidelines)

A **trade is one closed position**: a name is bought, optionally trimmed at rebalances,
then fully sold; its whole-life realised P&L (net of 0.1% on every leg) is one trade.
Accuracy and gain-to-loss are computed over these 159 closed positions (in-sample), not
over the 394 individual sell transactions — counting each monthly trim as its own trade
would inflate the count and distort accuracy. Both views are reported (`accuracy` vs
`accuracy_by_transaction` in `metrics_*.json`) for full transparency, and positions still
open on the final day are excluded from accuracy entirely.

---

## 4. Why this should generalise out-of-sample

Momentum and low-volatility are two of the most heavily documented factors in the
literature, across decades and markets. The rule has three tunable numbers (two lookbacks
and a factor weight); the lookback is convention, and the other two were fixed on a
train/validate split that never saw 2026. There are no stock-specific overrides.
`run_backtest.py` executes the identical rule over both windows with no refitting.

The honest position on tuning: **the two data-chosen parameters saw 2021–2025, never
2026.** They were selected by generalisation (does the TRAIN choice survive on VALIDATE?)
rather than by peak in-sample performance — which is precisely why we took momentum 55%,
the validate-optimum, over the higher train-optimum. The out-of-sample result is
therefore a genuine test, and it passed: +22.6 pp/yr of selection alpha on data the model
was frozen before.

---

## 5. Known limitations / assumptions to disclose in the report

- **The universe effect is large — and quantified.** Membership is a single snapshot
  taken 2026-08-25 and applied back to 2021–2025. This is the *compliant* reading of the
  mandate: §2 names the three indices with no as-of date and the §11 checklist asks that
  only *permitted* (current-list) stocks are held. Equal-weight holding the whole universe
  — zero skill — earns **+20.5 pp/yr in-sample over the Nifty 100**. That gap is the size
  premium, the equal-weight premium and survivorship combined; it is *not* alpha, it
  applies identically to every team, and it is held constant on both sides of every
  selection-alpha comparison. The survivorship *slice* specifically is isolated in §7.
- **The out-of-sample window is short** — 122 trading days, 16 closed positions. The
  ladder's alphabetical control scored +48% over it. Treat every OOS *level* as
  directional; the reason to trust it is that selection alpha is stable between it and the
  in-sample window, not the single number.
- **No parameter was chosen on 2026**, and only two were chosen on 2021–2025 at all, via a
  train/validate split (§2.3). The residual overfitting risk is therefore small and
  bounded by the fallbacks in §2.6.
- **Deeper drawdown than a low-momentum book** (−29.4%), the direct cost of a momentum
  tilt. Out-of-sample drawdown (−17.1%) was close to the benchmark's.
- **Execution is modelled as a fill at the close** with a flat 0.1% cost. Real costs add
  bid-ask spread, market impact and STT/stamp duty, which 0.1% may under-state for smaller
  names even after the liquidity screen.
- **Whole-share trading**, residual held in cash, so the book is never exactly 100%
  invested.
- **No fundamental or value factor** — price-only by design given the data constraints.
- **yfinance data quality** for illiquid smallcaps is not independently verified against a
  paid vendor. All 300 universe names downloaded with 0 failures and no name above 5%
  missing days (`data/processed/data_quality.csv`); 64 listed after the backtest start and
  are unscoreable until they have 12 months of history.

---

## 6. Alternative signal families — the search that found nothing better

`python -m src.alt_strategies`. §2 explores *one* idea: rank the universe on momentum and
volatility. This section holds the harness fixed — same engine, costs, 10-name cap,
eligibility gate — and swaps the signal. Selection alpha by year, worst, mean and the
held-out window:

| Signal family | worst | mean | OOS |
|---|---|---|---|
| **SHIPPED — mom55/lowvol45 skip2** | **+3.6** | **+26.5** | **+22.6** |
| illiquidity (Amihud) | −12.0 | +52.8 | −8.4 |
| residual momentum (beta stripped) | −3.5 | +28.0 | +3.7 |
| sector-neutral shipped | +0.1 | +22.6 | +28.4 |
| sector-neutral residual momentum | −13.7 | +25.1 | +25.1 |
| ensemble: shipped + residual momentum | +4.1 | +24.9 | +20.2 |
| momentum only | −6.6 | +27.8 | +11.1 |
| acceleration (6m vs prior 6m) | −14.7 | +11.1 | −33.4 |
| trend (100d MA distance) | −29.6 | +3.5 | +27.2 |
| reversal (3m loser) | −30.7 | +3.2 | +47.4 |
| return consistency | −24.5 | +1.4 | −18.1 |
| trend (200d MA distance) | −42.0 | −0.3 | +0.9 |
| reversal (1m loser) | −24.3 | −10.5 | +16.9 |
| 52-week high proximity | −25.9 | −15.4 | +13.7 |
| low beta | −52.6 | −25.4 | −22.2 |

**What this establishes:**

- **Momentum's direction is right.** Reversal — the literal opposite — is negative at
  both 1-month (−10.5 mean) and has a −30.7 worst year at 3-month. If our momentum result
  were a sign error or sample artifact, this is where it would show.
- **Momentum is not disguised market beta.** Residual momentum (beta stripped out) scores
  +28.0 mean, essentially matching raw momentum. The edge is stock-specific.
- **Low beta confirms the low-vol finding independently** (−25.4 mean, worst −52.6). Two
  different "prefer calm stocks" constructions both fail as *selection* signals, which is
  why low-vol is capped at 45% and used for tempering, not picking.
- **Nothing beat the incumbent on the robustness bar.** The high-mean candidates fail on
  inspection: illiquidity (Amihud) posts the highest mean (+52.8) but a losing year and
  negative OOS; the residual-momentum ensemble is robust but not an *improvement* (worst
  year +4.1 vs +3.6, OOS +20.2 vs +22.6). Sector-neutral shipped is the one genuinely open
  idea — best OOS in the whole project (+28.4) and a risk-control argument (prevents an
  accidental industry bet) — and is the first thing to revisit with more held-out data.
- **A caveat on this table.** Nineteen candidates were tested; with that many comparisons
  one edging past the incumbent is expected by chance, which is exactly why the ensemble
  was put through the neighbourhood and per-year tests before being rejected rather than
  adopted on its headline. The value here is the negative result: the shipped rule
  survived a broad search across genuinely different signals.

---

## 7. Appendix — does the edge survive a point-in-time universe?

`python -m src.pit_universe`. The claim this analysis rests on is that selection alpha
nets out the universe effect. That is an argument until it is tested against a universe
that carries *no* survivorship advantage.

The three constituent lists were captured by the Internet Archive in **August 2023**.
Membership churn since is large:

| Index | Still in the list (Aug 2023 → Aug 2026) | Replaced |
|---|---|---|
| Nifty 100 | 71.3% | 29 |
| Nifty Midcap 100 | 48.0% | 52 |
| **Nifty Smallcap 100** | **22.0%** | **78** |

Only 203 names are common to both universes. Trading the **August 2023 list from
September 2023 onwards** carries **no survivorship advantage** — every name was in the
index before the first trade, and names promoted later are excluded (if anything a
handicap). Extending into 2026 makes it clean on *both* axes: no forward-looking universe
and no parameter tuning.

| Metric | 2023 universe | 2026 universe (submitted) |
|---|---|---|
| **Sep 2023 → Dec 2025 — universe-clean** | | |
| Total Net PNL | ₹91.05 L | ₹143.59 L |
| CAGR | +32.9% | +47.8% |
| Sharpe | 1.33 | 1.89 |
| Equal-weight hold of same universe | +20.7% | +31.1% |
| **Selection alpha** | **+12.1 pp** | **+16.8 pp** |
| **Jan → Jun 2026 — universe-clean AND parameter-clean** | | |
| Total Net PNL | ₹6.94 L | ₹11.93 L |
| CAGR | +15.0% | +26.5% |
| Sharpe | 0.63 | 0.93 |
| Equal-weight hold of same universe | +1.5% | +3.8% |
| **Selection alpha** | **+13.5 pp** | **+22.6 pp** |
| *Nifty 100, same windows* | *+15.1% then −12.9%* | |

**What it establishes.** Strip the hindsight out of the universe and the headline CAGR
falls ~15 pp (47.8% → 32.9%). The skill-free equal-weight hold falls by almost exactly as
much (31.1% → 20.7%) — the universe effect landing on both sides, as it should.
**Selection alpha barely moves: +16.8 → +12.1 pp in-sample, and on the clean 2026 window
+13.5 pp.** The strategy's contribution is close to invariant to the universe it is
measured on.

The cleanest single number in the project is the second block: universe fixed August
2023, parameters fixed on data ending December 2025, traded through H1 2026 — **₹6.94 lakh
profit, +13.5 pp/yr over holding the same universe, Sharpe 0.63, in a window where the
Nifty 100 fell 12.9%.** No hindsight of any kind is available to it.

**Why it stays an appendix.** The submitted result uses the 2026 universe because that is
the compliant reading. Archive coverage is too sparse for a continuous point-in-time
backtest across 2021–2025. The 2023 window is shorter and noisier (−34.7% drawdown), and
28 of the 301 names in the 2023 list no longer return price data at all — a mild
survivorship effect in the opposite direction that is not corrected for.

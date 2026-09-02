# Executive Summary — Finesse × Citadel Round 2

**Strategy.** A systematic, long-only, 10-stock portfolio drawn monthly from the Nifty
100 / Midcap 100 / Smallcap 100 universe. We hold the ten most liquid names that best
combine **12-month price momentum (55%)** with **low recent volatility (45%)**, weight
winners more heavily subject to a 25% cap, and rebalance monthly with a turnover buffer.
No leverage, no shorts, 0.1% charged on every trade. It is a rules engine you can read in
an afternoon — no black box, no fundamentals we cannot source cleanly, no discretionary
overrides.

**Headline result (₹1 crore start).**

| | Backtest 2021–2025 | Held-out 2026 H1 |
|---|---|---|
| **Total Net PnL** | **₹8.99 crore** | **₹11.93 lakh** |
| CAGR | 60.0% | 26.5% |
| Sharpe (rf = 0%) | 2.42 | 0.93 |
| Max drawdown | −29.4% | −17.1% |
| vs Nifty 100 | +89.4% index | −6.4% index |

The out-of-sample half-year is the one that matters: the portfolio made **+11.9% while
both the Nifty 100 and Nifty 500 fell**, on a model that was frozen before that data
existed.

**What makes this credible, not just large.** A five-year Indian mid/small-cap bull run
flatters almost any long book, so we refuse to let the 899% headline stand on its own. We
benchmark against a skill-free equal-weight hold of our *own* universe, which strips out
the size, equal-weight and survivorship tailwinds that every team inherits. On that
bias-matched basis our **selection alpha is +25.5 pp/yr in-sample and +22.6 pp/yr
out-of-sample** — nearly identical across a genuinely held-out window. That stability,
not the raw return, is the evidence.

**We did not tune to the test.** Every parameter is either textbook/mandated or was
chosen on a **train (2021–2023) / validate (2024–2025) split that never touched 2026**.
Where the in-sample data begged us to push momentum weight to 65–80%, the validation set
said 50–55% generalises better — so we took 55% and left the higher in-sample number on
the table. The 2026 result was computed only after the model was frozen. This is the
"defensible process over hindsight" the brief asks for, made literal.

**Three stress tests we ran on ourselves.**
1. *Zero-skill controls* — random and alphabetical 10-stock portfolios score ≈0 selection
   alpha in-sample, confirming our measurement isn't crediting mere concentration.
2. *Point-in-time universe* — on the August-2023 constituent lists (78% of the Smallcap
   100 has since changed), with no survivorship advantage, the strategy still earns
   **+13.5 pp/yr selection alpha in a falling 2026 market**.
3. *14 alternative signals* — reversal, trend, low-beta, illiquidity, residual momentum,
   sector-neutral and ensemble variants. None beats the shipped rule on the bar that
   matters (positive every year *and* out-of-sample), and reversal's failure confirms our
   momentum signal has the right sign.

**Known limitations, stated plainly.** The universe snapshot carries survivorship bias
(quantified, ~+20 pp/yr, common to all teams); the out-of-sample window is short (trust
the stability of the edge, not the single level); 0.1% models explicit cost only; the book
is price-only by design. All are discussed in the report and none changes the conclusion.

**Bottom line.** ₹1 crore becomes ₹9.99 crore over the backtest and grows a further
₹11.93 lakh out-of-sample while the market falls — but the number we would defend to a
jury is the +22.6 pp/yr of out-of-sample selection alpha over our own universe, produced
by a rule that was frozen before it ever saw that data.

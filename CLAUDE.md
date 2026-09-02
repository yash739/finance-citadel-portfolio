# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repo is a **scaffold, not a working system**. Every module in `src/` is a stub:
functions either `raise NotImplementedError` or have `# TODO` comments describing what
to build. The universe CSVs (`data/universe/*.csv`) contain only header rows. Do not
assume any pipeline stage works until you've implemented/verified it — `run_backtest.py`
will fail immediately today because `data/processed/prices.parquet` doesn't exist and
`data_loader.download_prices` is unimplemented.

This is a submission for the "Finesse x Citadel" Round 2 case competition: build a
systematic, factor-based, long-only equity portfolio (≤10 stocks) from Nifty 100 /
Midcap 100 / Smallcap 100, backtest 1 Jan 2021–31 Dec 2025, then run it unmodified
out-of-sample over 1 Jan–30 Jun 2026. Submission deadline: 31 August. Every design choice
should be defensible to a jury, not just backtest-optimal — see
`docs/strategy_notes.md` for the "why this should generalise" reasoning that must be
written *before* looking at OOS results.

## Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m src.universe          # build/validate universe from data/universe/*.csv
python -m src.data_loader       # download OHLCV via yfinance -> data/processed/prices.parquet
python run_backtest.py --config config.yaml   # full pipeline -> reports/

pytest                          # run tests (tests/test_backtest.py is currently skipped)
pytest tests/test_backtest.py::test_backtest_toy_example -v   # single test
```

There is no lint/format tooling configured in this repo.

## Architecture

Pipeline, in order, wired together by `run_backtest.py`:

```
config.yaml -> universe.py -> data_loader.py -> factors.py -> portfolio.py -> backtest.py -> metrics.py / benchmark.py -> visualize.py -> reports/
```

- **`config.yaml`** is the single source of truth for dates, capital, transaction costs,
  rebalance frequency, and weighting scheme. Nothing from it should be hardcoded
  elsewhere — every module reads it fresh.
- **`src/universe.py`** merges the three index CSVs into one deduplicated universe
  DataFrame (`ticker, name, sector, indices`).
- **`src/data_loader.py`** downloads adjusted OHLCV via yfinance across
  `data_start`→`out_of_sample_end` (the extra lookback before `backtest_start` exists
  so 12-month momentum is computable from day 1), caches raw pulls to `data/raw/`
  (gitignored), and writes one aligned wide panel to `data/processed/prices.parquet`
  (also gitignored) — this parquet is what every downstream module consumes.
- **`src/factors.py`** turns the price panel into per-stock scores at each rebalance
  date (momentum, low-vol; kept price-only by design — see rationale in the module
  docstring and `docs/strategy_notes.md`). Must be a pure function: scores in are
  cross-sectionally z-scored and combined with fixed, documented weights — no
  stock-by-stock tuning.
- **`src/portfolio.py`** turns scores into holdings: `select_stocks` (rank + take top
  ≤10, with an optional hysteresis buffer to reduce churn) then `weight_stocks`
  (equal / score-proportional / inverse-vol, capped at `max_weight_per_stock` and
  renormalised). Pure function — no side effects — so `backtest.py` can call it fresh
  at every rebalance date.
- **`src/backtest.py`** is the correctness-critical module: event-driven accounting
  that walks rebalance dates, computes target weights via factors+portfolio, derives
  the trades needed to move from current to target holdings, charges
  `transaction_cost_pct` on the notional of **every** buy and sell, and carries NAV
  forward daily between rebalances. Returns both a daily NAV series *and* a trade log
  (date, ticker, side, shares, price, cost) — metrics needs the trade log, not just NAV,
  for accuracy/gain-to-loss/turnover. Build and hand-verify against a tiny synthetic
  example in `tests/test_backtest.py` before trusting it on real data.
- **`src/metrics.py`** / **`src/benchmark.py`** / **`src/visualize.py`** consume the
  backtest output only — total/annualised return, max drawdown, Sharpe (rf=0%),
  gain-to-loss, accuracy, turnover; benchmark NAV normalised to the same ₹1 crore
  starting capital for direct comparison; plots at dpi≥150 for the report.
- **`run_backtest.py`** runs the *same* pipeline twice — once over
  `backtest_start..backtest_end`, once over `out_of_sample_start..out_of_sample_end` —
  with no refitting in between, writing `reports/metrics_{label}.json`,
  `reports/trades_{label}.csv`, and `reports/figures/equity_curve_{label}.png`.

Ownership split (from README): Person A owns universe/data/factors/portfolio
(stock-selection side); Person B owns backtest/metrics/benchmark/visualize/tests
(engine + evaluation side, where correctness matters most since a bug here silently
invalidates every downstream number).

## Key constraints to preserve in any implementation

- ≤10 holdings at all times; universe restricted to Nifty 100 / Midcap 100 / Smallcap 100.
- ₹1,00,00,000 starting capital.
- 0.1% transaction cost on every buy and every sell (notional value), no exceptions.
- Out-of-sample window must use the *exact same* trained rule as the in-sample
  backtest — no refitting between the two `run_backtest.py` passes.
- Universe membership currently uses *today's* (2026) constituent lists applied
  retroactively to 2021–2025 — a disclosed simplification. Don't silently "fix" this by
  sourcing historical constituents unless asked; if it changes, the disclosure in
  `docs/strategy_notes.md` / the report's Limitations section must be updated too.
- `docs/strategy_notes.md` is the plain-language source of truth for the actual
  selection/weighting/rebalancing rules once decided — keep it in sync with the code,
  since it feeds directly into the report's Methodology section.
- `reports/REPORT_TEMPLATE.md` encodes the exact required structure and metrics table
  for the final written report (5–6 pages) — `reports/metrics.json` output must cover
  every metric that template requires.

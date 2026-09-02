# Finesse x Citadel — Round 2 Portfolio Construction

Systematic, factor-based long-only equity portfolio (≤10 stocks) built from the
Nifty 100 / Midcap 100 / Smallcap 100 universe, backtested 1 Jan 2021 – 31 Dec 2025
with a 1 Jan 2026 – 30 Jun 2026 out-of-sample stress test.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Refresh the investable universe from niftyindices.com (a snapshot is committed)
python -m src.universe --refresh

# 2. Download price data for the universe (writes to data/raw/)
python -m src.data_loader

# 3. Run the full backtest (config.yaml controls dates, capital, costs, weighting)
python run_backtest.py --config config.yaml

# Outputs land in reports/: figures/, metrics_*.json, trades_*.csv, round_trips_*.csv

# 4. Sanity-check the result: how much is the universe (size/EW/survivorship) vs strategy?
python -m src.diagnostics

# 4b. Show the parameters were chosen on a train/validate split, never on 2026 (no leakage)
python -m src.experiments --select

# 5. Reproduce the strategy-selection evidence (ladder, sweeps, per-year robustness)
python -m src.experiments --all

# 6. Check the edge is not an artifact of the current index snapshot
python -m src.pit_universe

# 7. Head-to-head against alternative signal families (reversal, trend, residual
#    momentum, low beta, illiquidity, sector-neutral, ensembles)
python -m src.alt_strategies
```

Environment: a conda env in WSL (`conda create -n citadel -c conda-forge python=3.11
pandas numpy pyyaml matplotlib scipy pytest pyarrow && pip install yfinance tqdm`).
All git remote operations run through WSL - port 22 is blocked on this network, so
`~/.ssh/config` routes github.com over port 443.

## Repo layout

```
config.yaml            single source of truth: dates, capital, txn cost, rebalance freq
data/
  universe/             static CSVs: nifty100.csv, midcap100.csv, smallcap100.csv (ticker, name, sector)
  universe_2023/        the same three lists as they stood in Aug 2023 (Internet Archive)
  raw/                  downloaded OHLCV, gitignored — regenerate via src/data_loader.py
  processed/            cleaned/adjusted panels used by the backtest
src/
  universe.py           builds/validates the eligible stock universe
  data_loader.py         pulls daily OHLCV (yfinance) for the universe + benchmark
  factors.py             factor computation (momentum, volatility, ...) -> scores
  portfolio.py            stock selection + weighting rule, given factor scores
  backtest.py             event-driven portfolio accounting: rebalancing, transaction costs, NAV path
  metrics.py               Sharpe, MDD, annualised return, gain-to-loss, accuracy, turnover
  benchmark.py              Nifty 100 / 500 comparison series
  visualize.py              equity curve, drawdown, rolling return plots
  diagnostics.py            return decomposition: index vs universe/composition vs selection
  experiments.py            strategy ladder + parameter sweeps: how the strategy was chosen
  pit_universe.py           2023 point-in-time universe test: is the edge snapshot-dependent?
  alt_strategies.py         14 alternative signal families + sector-neutral and ensemble wrappers
notebooks/                scratch/exploration only — final numbers must come from src/ + run_backtest.py
reports/                   generated outputs (figures, metrics.json) + the written report
  report.html              the written report: findings, ladder, sweeps, results (self-contained)
  build_chart_data.py      extracts the NAV series report.html plots
  REPORT_TEMPLATE.md       5-6 page report skeleton: guidelines structure, required metrics table, checklist
tests/                     unit tests for backtest accounting and metrics (correctness of the engine matters most)
docs/strategy_notes.md      the actual stock-selection / weighting / rebalancing rules in plain language
```

## Data sources

- **Prices**: `yfinance`, NSE tickers with a `.NS` suffix (e.g. `RELIANCE.NS`). Free, but
  double-check adjusted-close handling for splits/dividends and check for gaps around
  illiquid smallcap names.
- **Universe membership**: index constituents change over 2021–2025. Using *today's*
  constituent list for the whole backtest period introduces a small survivorship/look-ahead
  bias — acceptable given the timeline, but **disclose it explicitly** in the report's
  Limitations section rather than silently.
- **Benchmark**: Nifty 100 (`^CNX100` / `^NSEI100`, verify exact Yahoo ticker) or Nifty 500.


## Reproducibility checklist before submitting

- [ ] `pip install -r requirements.txt && python run_backtest.py` runs clean on a fresh clone
- [ ] All dates, capital, and cost assumptions live in `config.yaml`, not hardcoded
- [ ] Universe restricted to Nifty 100 / Midcap 100 / Smallcap 100, ≤10 holdings at all times
- [ ] 0.1% transaction cost applied on every buy and sell
- [ ] `reports/metrics_in_sample.json` and `reports/metrics_out_of_sample.json` contain
      every metric required by the guidelines
- [ ] Benchmark comparison included and plotted
- [ ] Out-of-sample run (Jan–Jun 2026) uses the exact same trained rule, no refitting;
      the two data-chosen parameters were fixed on a 2021–2023 / 2024–2025 train-validate
      split (`python -m src.experiments --select`), never on the 2026 window
- [ ] `pytest tests/ -q` passes (124 tests, incl. a no-look-ahead invariance check)
- [ ] Universe/composition effect (size + equal-weight + survivorship) quantified and
      disclosed, not just mentioned - see `python -m src.diagnostics`, the point-in-time
      survivorship test `python -m src.pit_universe`, and docs/strategy_notes.md

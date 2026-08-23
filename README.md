# Finesse x Citadel — Round 2 Portfolio Construction

Systematic, factor-based long-only equity portfolio (≤10 stocks) built from the
Nifty 100 / Midcap 100 / Smallcap 100 universe, backtested 1 Jan 2021 – 31 Dec 2025
with a 1 Jan 2026 – 30 Jun 2026 out-of-sample stress test.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Build/refresh the investable universe list
python -m src.universe

# 2. Download price data for the universe (writes to data/raw/)
python -m src.data_loader

# 3. Run the full backtest (config.yaml controls dates, capital, costs, weighting)
python run_backtest.py --config config.yaml

# Outputs land in reports/: equity_curve.png, drawdown.png, metrics.json, trades.csv
```

## Repo layout

```
config.yaml            single source of truth: dates, capital, txn cost, rebalance freq
data/
  universe/             static CSVs: nifty100.csv, midcap100.csv, smallcap100.csv (ticker, name, sector)
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
notebooks/                scratch/exploration only — final numbers must come from src/ + run_backtest.py
reports/                   generated outputs (figures, metrics.json) + the written 5-6 page report
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

## Team split

See the shared plan doc for the full breakdown — short version: one person owns data +
factors + stock selection (`universe.py`, `data_loader.py`, `factors.py`, `portfolio.py`),
the other owns the backtest engine + evaluation (`backtest.py`, `metrics.py`,
`benchmark.py`, `visualize.py`, `tests/`). Both write the report together once results
are in.

## Reproducibility checklist before submitting

- [ ] `pip install -r requirements.txt && python run_backtest.py` runs clean on a fresh clone
- [ ] All dates, capital, and cost assumptions live in `config.yaml`, not hardcoded
- [ ] Universe restricted to Nifty 100 / Midcap 100 / Smallcap 100, ≤10 holdings at all times
- [ ] 0.1% transaction cost applied on every buy and sell
- [ ] `reports/metrics.json` contains every metric required by the guidelines
- [ ] Benchmark comparison included and plotted
- [ ] Out-of-sample run (Jan–Jun 2026) uses the exact same trained rule, no refitting

"""
Download and cache daily OHLCV data for the universe + benchmark.

OWNER: Person A (data/strategy)

TODO:
- Pull daily adjusted OHLCV via yfinance for every ticker in the universe, plus
  the benchmark ticker from config.yaml, spanning config.dates.data_start through
  config.dates.out_of_sample_end.
- Cache raw pulls to data/raw/<ticker>.csv so reruns don't re-hit the network.
- Build a single cleaned, aligned price panel (dates x tickers, adjusted close)
  in data/processed/prices.parquet — this is what factors.py and backtest.py consume.
- Handle: missing data / late listings (a stock IPO'd after 2021), stale/illiquid
  names with zero-volume days, and stock splits (yfinance auto-adjusts close, but
  double check volume/turnover fields if you use them).
- Log which tickers failed to download or have >X% missing days — that list
  belongs in the report's Limitations section.
"""

import yaml
import pandas as pd
import yfinance as yf
from pathlib import Path

from src.universe import load_universe


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def download_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Download adjusted close for `tickers` between start/end (inclusive-ish).

    Returns a wide DataFrame indexed by date, one column per ticker.
    """
    # TODO: batch via yf.download(tickers, start=start, end=end, auto_adjust=True)
    # and cache per-ticker to data/raw/. Watch yfinance rate limits with ~300 tickers.
    raise NotImplementedError


if __name__ == "__main__":
    cfg = load_config()
    universe = load_universe()
    tickers = universe["ticker"].unique().tolist() + [cfg["benchmark"]["ticker"]]
    prices = download_prices(tickers, cfg["dates"]["data_start"], cfg["dates"]["out_of_sample_end"])
    out = Path("data/processed")
    out.mkdir(parents=True, exist_ok=True)
    prices.to_parquet(out / "prices.parquet")
    print(f"Saved price panel: {prices.shape[0]} days x {prices.shape[1]} tickers.")

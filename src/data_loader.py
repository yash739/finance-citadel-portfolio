"""
Download and cache daily OHLCV data for the universe + benchmark.

OWNER: Person A (data/strategy)

Produces three artefacts under data/processed/ (all gitignored - regenerate with
`python -m src.data_loader`):

  prices.parquet       dates x tickers, split/dividend-adjusted close
  volumes.parquet      dates x tickers, raw traded volume (drives the liquidity filter)
  data_quality.csv     per-ticker coverage stats + the reason any ticker was dropped

ADJUSTED vs RAW CLOSE: we pull with auto_adjust=True, so `Close` is adjusted for
splits and dividends. That is the correct series for return computation - using raw
close would inject a fake -50% return on every split date. Volume is not adjusted on
the same basis, so the liquidity filter works in rupee turnover (close x volume)
rather than raw share count.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import yaml

from src.universe import load_universe

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")

# yfinance throttles aggressively past ~50 symbols in one call.
BATCH_SIZE = 40
MAX_RETRIES = 3


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _cache_path(ticker: str) -> Path:
    safe = ticker.replace("/", "_").replace("^", "IDX_")
    return RAW_DIR / (safe + ".csv")


def _read_cached(ticker: str, start: str, end: str):
    """Return the cached frame for `ticker` if it exists and reaches close to `end`."""
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
    except Exception:
        return None
    if df.empty:
        return None
    # A cache that stops well before `end` is stale. A cache that *starts* late is
    # fine - that just means the stock listed after our data_start.
    if df.index.max() < pd.Timestamp(end) - pd.Timedelta(days=7):
        return None
    return df


def _download_batch(tickers, start: str, end: str) -> dict:
    """Download a batch of tickers, returning {ticker: OHLCV frame}."""
    import yfinance as yf

    out: dict = {}
    data = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = yf.download(
                tickers,
                start=start,
                end=end,
                auto_adjust=True,
                group_by="ticker",
                progress=False,
                threads=True,
            )
            break
        except Exception as exc:  # network flake / rate limit
            if attempt == MAX_RETRIES:
                print("  batch failed after %d attempts: %s" % (MAX_RETRIES, exc))
                return out
            time.sleep(2 * attempt)

    if data is None or len(data) == 0:
        return out

    for t in tickers:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if t not in data.columns.get_level_values(0):
                    continue
                sub = data[t].dropna(how="all")
            else:
                sub = data.dropna(how="all")
            if len(sub) > 0:
                out[t] = sub
        except Exception:
            continue
    return out


def download_prices(tickers, start: str, end: str, use_cache: bool = True):
    """Download adjusted close + volume for `tickers` between start/end.

    Returns (prices, volumes, quality): prices/volumes are wide DataFrames indexed
    by date with one column per ticker; quality is a per-ticker coverage report.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    frames: dict = {}
    to_fetch: list = []

    if use_cache:
        for t in tickers:
            cached = _read_cached(t, start, end)
            if cached is not None:
                frames[t] = cached
            else:
                to_fetch.append(t)
    else:
        to_fetch = list(tickers)

    print("%d tickers served from cache, %d to download." % (len(frames), len(to_fetch)))

    for i in range(0, len(to_fetch), BATCH_SIZE):
        batch = to_fetch[i : i + BATCH_SIZE]
        print("  downloading %d-%d of %d ..." % (i + 1, i + len(batch), len(to_fetch)))
        got = _download_batch(batch, start, end)
        for t, df in got.items():
            df.to_csv(_cache_path(t))
            frames[t] = df
        time.sleep(1)  # be polite to Yahoo between batches

    failed = sorted(set(tickers) - set(frames))
    if failed:
        shown = ", ".join(failed[:10]) + (" ..." if len(failed) > 10 else "")
        print("  %d ticker(s) returned no data: %s" % (len(failed), shown))

    close = pd.DataFrame({t: df["Close"] for t, df in frames.items() if "Close" in df})
    volume = pd.DataFrame({t: df["Volume"] for t, df in frames.items() if "Volume" in df})

    close = close.sort_index()
    volume = volume.reindex(index=close.index, columns=close.columns)

    quality = _quality_report(close, volume, tickers, failed)
    return close, volume, quality


def _quality_report(close, volume, requested, failed):
    """Per-ticker coverage stats - raw material for the report's Limitations section."""
    rows = []
    for t in requested:
        if t in failed or t not in close.columns:
            rows.append(
                {
                    "ticker": t,
                    "status": "no_data",
                    "first_date": pd.NaT,
                    "last_date": pd.NaT,
                    "n_obs": 0,
                    "pct_missing": 1.0,
                    "n_zero_volume_days": -1,
                }
            )
            continue
        s = close[t]
        first = s.first_valid_index()
        last = s.last_valid_index()
        # Missing days are measured only over the ticker's own listed life, so a
        # late IPO is not double-counted as "missing data".
        if first is not None and last is not None:
            pct_missing = float(s.loc[first:last].isna().mean())
        else:
            pct_missing = 1.0
        zero_vol = int((volume[t].fillna(0) == 0).sum()) if t in volume.columns else -1
        rows.append(
            {
                "ticker": t,
                "status": "ok" if s.notna().sum() > 0 else "no_data",
                "first_date": first if first is not None else pd.NaT,
                "last_date": last if last is not None else pd.NaT,
                "n_obs": int(s.notna().sum()),
                "pct_missing": round(pct_missing, 4),
                "n_zero_volume_days": zero_vol,
            }
        )

    q = pd.DataFrame(rows)
    if len(close) > 0:
        cutoff = close.index.min() + pd.Timedelta(days=30)
        q["late_listing"] = pd.to_datetime(q["first_date"]).gt(cutoff).fillna(False)
    else:
        q["late_listing"] = False
    return q


def build_panel(config: dict, use_cache: bool = True) -> None:
    """End-to-end: universe -> download -> cleaned panels on disk."""
    universe = load_universe(config["universe"]["sources"])
    benchmark = config["benchmark"]["ticker"]
    tickers = universe["ticker"].unique().tolist() + [benchmark]
    secondary = config["benchmark"].get("secondary_ticker")
    if secondary and secondary not in tickers:
        tickers.append(secondary)

    prices, volumes, quality = download_prices(
        tickers,
        config["dates"]["data_start"],
        config["dates"]["out_of_sample_end"],
        use_cache=use_cache,
    )

    # Forward-fill short gaps (trading halts) but never fabricate a price before a
    # stock's first real trade or after its last - that would invent returns.
    prices = prices.ffill(limit=5)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    prices.to_parquet(PROCESSED_DIR / "prices.parquet")
    volumes.to_parquet(PROCESSED_DIR / "volumes.parquet")
    quality.to_csv(PROCESSED_DIR / "data_quality.csv", index=False)

    n_bad = int((quality["status"] != "ok").sum())
    n_late = int(quality["late_listing"].sum())
    n_gappy = int((quality["pct_missing"] > 0.05).sum())
    bench_state = "PRESENT" if benchmark in prices.columns else "MISSING - fix config.yaml"
    print(
        "\nSaved price panel: %d days x %d tickers.\n"
        "  benchmark %s: %s\n"
        "  tickers with no data:        %d\n"
        "  tickers listed after start:  %d\n"
        "  tickers >5%% missing days:    %d\n"
        "  full report -> %s"
        % (
            prices.shape[0],
            prices.shape[1],
            benchmark,
            bench_state,
            n_bad,
            n_late,
            n_gappy,
            PROCESSED_DIR / "data_quality.csv",
        )
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--no-cache", action="store_true", help="Force re-download.")
    args = parser.parse_args()
    build_panel(load_config(args.config), use_cache=not args.no_cache)

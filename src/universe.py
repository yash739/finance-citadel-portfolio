"""
Build and validate the eligible stock universe (Nifty 100 + Midcap 100 + Smallcap 100).

OWNER: Person A (data/strategy)

The three CSVs under data/universe/ are a *committed snapshot* of index membership
pulled from niftyindices.com. They are checked into git deliberately: the backtest
must be reproducible on a fresh clone without depending on NSE's site being up, and
the snapshot date must be visible to anyone auditing the numbers.

SURVIVORSHIP / LOOK-AHEAD BIAS — the disclosure that belongs in the report:
membership is a single snapshot applied retroactively across 2021-2025. A stock that
was in the Nifty 100 in 2021 but was demoted before 2026 is absent from our universe,
and a stock promoted into the index in 2024 is treated as eligible back in 2021. That
biases results upward, because index promotion follows good performance. It is a
disclosed simplification forced by the lack of free point-in-time constituent data,
not a bug — see docs/strategy_notes.md and the report's Limitations section.

Refresh the snapshot with:  python -m src.universe --refresh
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

import pandas as pd

UNIVERSE_FILES = [
    "data/universe/nifty100.csv",
    "data/universe/midcap100.csv",
    "data/universe/smallcap100.csv",
]

# NSE publishes each index's constituents as a plain CSV at a stable URL.
INDEX_SOURCES = {
    "nifty100": (
        "Nifty 100",
        "https://niftyindices.com/IndexConstituent/ind_nifty100list.csv",
    ),
    "midcap100": (
        "Nifty Midcap 100",
        "https://niftyindices.com/IndexConstituent/ind_niftymidcap100list.csv",
    ),
    "smallcap100": (
        "Nifty Smallcap 100",
        "https://niftyindices.com/IndexConstituent/ind_niftysmallcap100list.csv",
    ),
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/csv,*/*",
    "Referer": "https://niftyindices.com/",
}


def fetch_index_constituents(key: str, timeout: int = 30) -> pd.DataFrame:
    """Download one index's live constituent list from niftyindices.com.

    Returns a DataFrame with our canonical columns: ticker, name, sector, index.
    `ticker` is the Yahoo Finance symbol (NSE symbol + ".NS").
    """
    index_name, url = INDEX_SOURCES[key]
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8-sig")

    from io import StringIO

    df = pd.read_csv(StringIO(raw))
    out = pd.DataFrame(
        {
            "ticker": df["Symbol"].str.strip() + ".NS",
            "name": df["Company Name"].str.strip(),
            "sector": df["Industry"].str.strip(),
            "index": index_name,
        }
    )
    return out.sort_values("ticker").reset_index(drop=True)


def refresh_universe_files(snapshot_date: str, out_dir: str = "data/universe") -> None:
    """Re-download all three constituent lists and overwrite the committed snapshot.

    `snapshot_date` is written into each file as a comment so the vintage of the
    membership data is self-documenting.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for key, (index_name, url) in INDEX_SOURCES.items():
        df = fetch_index_constituents(key)
        path = out / f"{key}.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(f"# {index_name} constituents\n")
            f.write(f"# Snapshot date: {snapshot_date}\n")
            f.write(f"# Source: {url}\n")
            f.write(
                "# Applied retroactively across the whole backtest - see the "
                "survivorship-bias note in src/universe.py.\n"
            )
            df.to_csv(f, index=False)
        print(f"Wrote {len(df):3d} constituents -> {path}")


def load_universe(files=UNIVERSE_FILES) -> pd.DataFrame:
    """Load and merge the universe CSVs into one deduplicated DataFrame.

    Expected columns per file: ticker, name, sector, index
    Returns: DataFrame with columns [ticker, name, sector, indices] where
    `indices` is a list of the index name(s) the ticker appears in.
    """
    frames = []
    for f in files:
        path = Path(f)
        if not path.exists():
            raise FileNotFoundError(
                f"{f} not found - refresh it with `python -m src.universe --refresh`."
            )
        # comment="#" skips the snapshot-provenance header block.
        df = pd.read_csv(path, comment="#")
        missing = {"ticker", "name", "sector", "index"} - set(df.columns)
        if missing:
            raise ValueError(f"{f} is missing required column(s): {sorted(missing)}")
        if df.empty:
            raise ValueError(
                f"{f} has a header but no rows - it is still a placeholder. "
                "Run `python -m src.universe --refresh`."
            )
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    combined["ticker"] = combined["ticker"].str.strip().str.upper()

    # Collapse index membership into a list column, keeping one row per ticker.
    indices = (
        combined.groupby("ticker")["index"]
        .agg(lambda s: sorted(set(s)))
        .rename("indices")
    )
    deduped = (
        combined.drop_duplicates(subset="ticker", keep="first")
        .drop(columns="index")
        .merge(indices, on="ticker", how="left")
        .sort_values("ticker")
        .reset_index(drop=True)
    )
    return deduped


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the eligible stock universe.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-download constituent lists from niftyindices.com and overwrite the snapshot.",
    )
    parser.add_argument(
        "--snapshot-date",
        default=None,
        help="Date to stamp into refreshed files (YYYY-MM-DD). Defaults to today.",
    )
    args = parser.parse_args()

    if args.refresh:
        from datetime import date

        refresh_universe_files(args.snapshot_date or date.today().isoformat())

    df = load_universe()
    n_overlap = (df["indices"].str.len() > 1).sum()
    print(f"Loaded {len(df)} unique tickers across {len(UNIVERSE_FILES)} index files.")
    print(f"  tickers appearing in more than one index: {n_overlap}")
    print(f"  sectors represented: {df['sector'].nunique()}")

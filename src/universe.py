"""
Build and validate the eligible stock universe (Nifty 100 + Midcap 100 + Smallcap 100).

OWNER: Person A (data/strategy)

TODO:
- Populate data/universe/nifty100.csv, midcap100.csv, smallcap100.csv with
  columns: ticker,name,sector,index (ticker = Yahoo Finance symbol, e.g. RELIANCE.NS).
  Source current constituents from niftyindices.com factsheets (each index page
  has a downloadable CSV of constituents). Use one consistent snapshot date and
  record it in the docstring/comment at the top of each CSV.
- Decide + document how you're handling the survivorship-bias tradeoff (see README):
  using today's constituents for 2021-2025 is a disclosed simplification, not a bug.
- load_universe() should return a single deduplicated DataFrame across all three
  indices with a column flagging which index(es) each stock belongs to.
"""

import pandas as pd
from pathlib import Path

UNIVERSE_FILES = [
    "data/universe/nifty100.csv",
    "data/universe/midcap100.csv",
    "data/universe/smallcap100.csv",
]


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
                f"{f} not found — populate it first (see TODO in this file)."
            )
        frames.append(pd.read_csv(path))
    combined = pd.concat(frames, ignore_index=True)
    # TODO: dedupe on ticker, collapse `index` into a list column `indices`
    return combined


if __name__ == "__main__":
    df = load_universe()
    print(f"Loaded {len(df)} universe rows across {len(UNIVERSE_FILES)} index files.")

"""Extract the NAV series that reports/report.html plots.

Run from the repo root:  python reports/build_chart_data.py
Writes reports/_chartdata.json, which is then inlined into report.html.
"""

import sys
from pathlib import Path

# This script lives in reports/, so Python puts reports/ on sys.path rather than
# the repo root - src/ would not import without this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json, pandas as pd, yaml
from src.universe import load_universe
from src.diagnostics import equal_weight_universe
from src.benchmark import load_benchmark

cfg = yaml.safe_load(open("config.yaml"))
cap = cfg["capital"]["starting_value_inr"]
prices = pd.read_parquet("data/processed/prices.parquet"); prices.index = pd.to_datetime(prices.index)
uni = load_universe(cfg["universe"]["sources"])

out = {}
for label, key in [("is","in_sample"), ("oos","out_of_sample")]:
    s, e = (cfg["dates"]["backtest_start"], cfg["dates"]["backtest_end"]) if label=="is" \
           else (cfg["dates"]["out_of_sample_start"], cfg["dates"]["out_of_sample_end"])
    win = prices.loc[s:e]
    nav = pd.read_csv("reports/nav_%s.csv" % key, index_col=0, parse_dates=True).iloc[:,0]
    ew  = equal_weight_universe(win, uni["ticker"], cap)
    idx = load_benchmark(win, cfg["benchmark"]["ticker"], cap)
    df = pd.DataFrame({"strategy": nav, "ew": ew, "index": idx}).dropna()
    step = max(1, len(df)//180)          # downsample for a compact payload
    keep = list(range(0, len(df), step))
    if keep[-1] != len(df) - 1:
        keep.append(len(df) - 1)         # never drop the final NAV - it is the headline
    df = df.iloc[keep]
    out[label] = {
        "dates": [d.strftime("%Y-%m-%d") for d in df.index],
        "strategy": [round(v/1e7, 4) for v in df["strategy"]],
        "ew":       [round(v/1e7, 4) for v in df["ew"]],
        "index":    [round(v/1e7, 4) for v in df["index"]],
    }
print(json.dumps(out)[:200])
json.dump(out, open("reports/_chartdata.json","w"))
print("\npoints:", len(out["is"]["dates"]), len(out["oos"]["dates"]))
print("IS final:", out["is"]["strategy"][-1], out["is"]["ew"][-1], out["is"]["index"][-1])
print("OOS final:", out["oos"]["strategy"][-1], out["oos"]["ew"][-1], out["oos"]["index"][-1])

# ---------------------------------------------------------------------------
# Continuous run: 2021-01-01 -> 2026-06-30 in ONE pass, so the equity curve can
# show the backtest and the held-out window on a single timeline with the
# handover marked.
#
# This is deliberately NOT the same as concatenating the two runs in
# run_backtest.py. Those are two independent Rs 1 crore deployments, and each
# reports standalone metrics. Here the book simply carries across 2025-12-31
# into 2026, which is what actually holding the strategy would have looked like.
# The tables in the report use the two-window figures; this series is for the
# chart only, and the report says so.
from src.backtest import run_backtest

full_start = cfg["dates"]["backtest_start"]
full_end   = cfg["dates"]["out_of_sample_end"]
volumes = pd.read_parquet("data/processed/volumes.parquet")
volumes.index = pd.to_datetime(volumes.index)

win  = prices.loc[full_start:full_end]
vwin = volumes.loc[full_start:full_end]
hist  = prices.loc[:full_start].iloc[:-1]
vhist = volumes.loc[:full_start].iloc[:-1]

res = run_backtest(win, uni, cfg, volumes=vwin, history=hist, volume_history=vhist)
nav_full = res["nav"]
ew_full  = equal_weight_universe(win, uni["ticker"], cap)
idx_full = load_benchmark(win, cfg["benchmark"]["ticker"], cap)

df = pd.DataFrame({"strategy": nav_full, "ew": ew_full, "index": idx_full}).dropna()
step = max(1, len(df)//240)
keep = list(range(0, len(df), step))
if keep[-1] != len(df) - 1:
    keep.append(len(df) - 1)
df = df.iloc[keep]

oos_start = pd.Timestamp(cfg["dates"]["out_of_sample_start"])
split = int((df.index < oos_start).sum())      # first index belonging to the held-out window

out["full"] = {
    "dates": [d.strftime("%Y-%m-%d") for d in df.index],
    "strategy": [round(v/1e7, 4) for v in df["strategy"]],
    "ew":       [round(v/1e7, 4) for v in df["ew"]],
    "index":    [round(v/1e7, 4) for v in df["index"]],
    "splitIndex": split,
    "splitDate": cfg["dates"]["out_of_sample_start"],
}
json.dump(out, open("reports/_chartdata.json", "w"))
print("continuous run: %d points, split at index %d (%s)"
      % (len(df), split, df.index[split].date()))
print("  at handover : strategy %.2f Cr | ew %.2f Cr | index %.2f Cr"
      % (df["strategy"].iloc[split-1]/1e7, df["ew"].iloc[split-1]/1e7, df["index"].iloc[split-1]/1e7))
print("  at 2026-06  : strategy %.2f Cr | ew %.2f Cr | index %.2f Cr"
      % (df["strategy"].iloc[-1]/1e7, df["ew"].iloc[-1]/1e7, df["index"].iloc[-1]/1e7))

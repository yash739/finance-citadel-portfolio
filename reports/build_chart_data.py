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

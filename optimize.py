"""Systematic search for more trades + high win rate, with honest time split.
  choose on 2023-2024 (train) -> check 2025 (validation) -> report 2026 (test, never used to choose).
"""
import sys, json, itertools
import pandas as pd, numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/claude")
import backtest as bt

D = "/tmp/claude-0/data/BaseMax_XAUUSD-LSTM/XAU_15m_data.csv"
DATA = None


def init():
    global DATA
    DATA = {y: bt.load(D, a, b) for y, (a, b) in
            {"2023": ("2023-01-01", "2024-01-01"), "2024": ("2024-01-01", "2025-01-01"), "2025": ("2025-01-01", "2025-10-01")}.items()}
    d = pd.read_csv("/tmp/claude-0/data/gdf/XAUUSD_15m.csv", parse_dates=["datetime"])
    sv = d.datetime.dt.tz_convert("America/New_York").dt.tz_localize(None) + pd.Timedelta(hours=7)
    DATA["2026"] = pd.DataFrame(dict(t=sv, open=d.open, high=d.high, low=d.low, close=d.close)).sort_values("t").reset_index(drop=True)


BASE = dict(brk=False, trend=True, be=False, cont_body=300, fvg=True, round_tp=True, ema=200)
GRID = dict(rsi_reg=[0, 40], bias=[None, "d"], adx_min=[0, 20], max_per_zone=[1, 2], min_away=[300, 500, 750],
            tp_pts=[700, 1000], rsi_entry=[0, 4], cont=[True, False])


def job(params):
    cfg = {**BASE, **params, "max_cont": 1}
    out = {"params": params}
    for y, m in DATA.items():
        tr = bt.run(m, cfg)
        if len(tr):
            eq = tr.sort_values("close_t").usd.cumsum()
            dd = (eq - np.maximum.accumulate(np.r_[0, eq.values])[1:]).min()
            w = tr[tr.usd > 0].usd.sum(); l = -tr[tr.usd < 0].usd.sum()
            out[y] = dict(n=len(tr), win=(tr.usd > 0).mean(), net=tr.usd.sum(), gw=w, gl=l, dd=dd)
        else:
            out[y] = dict(n=0, win=0, net=0, gw=0, gl=0, dd=0)
    return out


def agg(o, ys):
    n = sum(o[y]["n"] for y in ys)
    if n == 0:
        return dict(n=0, win=0, net=0, pf=0, dd=0)
    win = sum(o[y]["win"] * o[y]["n"] for y in ys) / n
    gw = sum(o[y]["gw"] for y in ys); gl = sum(o[y]["gl"] for y in ys)
    return dict(n=n, win=round(win * 100, 1), net=round(sum(o[y]["net"] for y in ys), 1),
                pf=round(gw / gl, 2) if gl else 9.9, dd=round(min(o[y]["dd"] for y in ys), 1))


if __name__ == "__main__":
    keys = list(GRID)
    combos = [dict(zip(keys, v)) for v in itertools.product(*GRID.values())]
    with Pool(2, initializer=init) as p:
        res = p.map(job, combos, chunksize=4)
    rows = []
    for o in res:
        r = {"params": json.dumps(o["params"])}
        for lab, ys in [("tr", ["2023", "2024"]), ("va", ["2025"]), ("te", ["2026"])]:
            a = agg(o, ys)
            for k, v in a.items():
                r[f"{lab}_{k}"] = v
        rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv("/tmp/claude-0/opt_results.csv", index=False)
    print("done", len(df))

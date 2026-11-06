"""Coach EP.1.1: 'ชนแนวรับต้านแท่งคู่ -> ถอดไส้กระสือ -> แท่งกลืนกิน cf PA -> Gab'
On M1 (or M5): price touches an H1 pair zone; a wick candle (กระสือ: wick >= w of range) whose wick
reaches into/through the zone; within N bars an engulfing candle closes beyond the กระสือ's body extreme
in the zone direction -> enter next open. SL beyond wick extreme + buf. TP = rr x risk.
"""
import sys, json
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude")
import m1_trick as mt

P = lambda x: x * 0.01


def run(base, tf_min=1, wick=0.5, win=5, buf=100, rr=1.2, max_sl=1500, min_away=500, spread=0.30, trend=False):
    b = base.set_index("t").resample(f"{tf_min}min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
    h1 = base.set_index("t").resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
    ema = h1.close.ewm(span=200, adjust=False).mean()
    trend_at = pd.Series(np.sign(h1.close - ema).values, index=h1.t + pd.Timedelta(hours=1))
    Z = mt.zones_h1(h1, mt.DEF)
    T = b.t.values; O, H, L, C = (b[c].values for c in ["open", "high", "low", "close"])
    trades = []; zi = 0; act = []; pos = None
    for i in range(1, len(b) - 1):
        t = pd.Timestamp(T[i])
        while zi < len(Z) and Z[zi]["formed"] <= t:
            z = dict(Z[zi]); z.update(away=False, k=None, used=False, dead=False, exp=z["formed"] + pd.Timedelta(hours=48)); act.append(z); zi += 1
        if pos:
            d = pos["d"]
            if (d > 0 and L[i] <= pos["sl"]) or (d < 0 and H[i] >= pos["sl"]):
                trades.append(dict(t=pos["t"], d=d, usd=(pos["sl"] - pos["e"]) * d - spread, res="SL", risk=pos["r"])); pos = None
            elif (d > 0 and H[i] >= pos["tp"]) or (d < 0 and L[i] <= pos["tp"]):
                trades.append(dict(t=pos["t"], d=d, usd=(pos["tp"] - pos["e"]) * d - spread, res="TP", risk=pos["r"])); pos = None
        for z in act:
            if z["dead"] or z["used"]:
                continue
            if t >= z["exp"] or (z["dir"] > 0 and C[i] < z["bot"] - P(300)) or (z["dir"] < 0 and C[i] > z["top"] + P(300)):
                z["dead"] = True; continue
            d = z["dir"]
            if not z["away"]:
                if (H[i] - z["top"] if d > 0 else z["bot"] - L[i]) >= P(min_away):
                    z["away"] = True
                continue
            rng = H[i] - L[i]
            # กระสือ candle: wick toward zone, reaching it
            wk = (min(O[i], C[i]) - L[i]) if d > 0 else (H[i] - max(O[i], C[i]))
            reach = (L[i] <= z["top"]) if d > 0 else (H[i] >= z["bot"])
            if reach and rng > 0 and wk >= wick * rng:
                z["k"] = dict(i=i, ext=L[i] if d > 0 else H[i], body=max(O[i], C[i]) if d > 0 else min(O[i], C[i]))
                continue
            k = z["k"]
            if k is None:
                continue
            if i - k["i"] > win:
                z["k"] = None; continue
            k["ext"] = min(k["ext"], L[i]) if d > 0 else max(k["ext"], H[i])
            cf = (C[i] > O[i] and C[i] > H[i - 1] and C[i] > k["body"]) if d > 0 else (C[i] < O[i] and C[i] < L[i - 1] and C[i] < k["body"])
            if cf and pos is None:
                if trend:
                    tr = trend_at[:t]
                    if len(tr) and tr.iloc[-1] != d:
                        z["k"] = None; continue
                e = O[i + 1]; sl = k["ext"] - d * P(buf); r = (e - sl) * d
                if 0 < r <= P(max_sl):
                    pos = dict(d=d, e=e, sl=sl, tp=e + d * rr * r, t=pd.Timestamp(T[i + 1]), r=r / 0.01)
                    z["used"] = True
                z["k"] = None
        act = [z for z in act if not z["dead"]]
    return pd.DataFrame(trades)


def st(tr):
    if tr.empty:
        return {}
    eq = tr.usd.cumsum(); dd = (eq - np.maximum.accumulate(np.r_[0, eq.values])[1:]).min()
    w = tr[tr.usd > 0].usd.sum(); l = -tr[tr.usd < 0].usd.sum()
    return dict(n=len(tr), win=round((tr.usd > 0).mean() * 100, 1), net=round(tr.usd.sum(), 1), pf=round(w / l, 2) if l else None,
                dd=round(dd, 1), risk_pts=int(tr.risk.median()))


if __name__ == "__main__":
    m1 = mt.load_m1("/tmp/claude-0/data/Sai310421_xauusd-data/csv/XAUUSD/XAUUSD_M1_2026Q1Q2.csv")
    mid = pd.Timestamp("2026-04-10")
    for name, kw in [("M1 rr1.2", {}), ("M1 rr1.0", {"rr": 1.0}), ("M1 rr1.5", {"rr": 1.5}), ("M1 rr1.2 ตามเทรน", {"trend": True}),
                     ("M5 rr1.2", {"tf_min": 5}), ("M5 rr1.2 ตามเทรน", {"tf_min": 5, "trend": True}), ("M1 ไส้>=0.6", {"wick": 0.6})]:
        tr = run(m1, **kw)
        a = tr[tr.t < mid].usd.sum() if len(tr) else 0; b = tr[tr.t >= mid].usd.sum() if len(tr) else 0
        print(name, json.dumps(st(tr)), f"| ครึ่งแรก {a:+.0f} ครึ่งหลัง {b:+.0f}", flush=True)

"""Coach's "small trick" (LINE 6 Nov 2026):
  at a big H1 pair-candle zone, RSI(14) on M1 hits oversold/overbought and an M1 candle
  rejects with a wick ("ถอดไส้") -> enter at once; optional small adds on the next wick-off;
  take 500-600 (or ~900) points; SL just past the wick.
Simulated on M1 bars. 0.01 lot = $1 per $1. Spread $0.30 per entry. SL checked before TP.
"""
import sys, json, itertools
import numpy as np, pandas as pd

P = lambda x: x * 0.01
DEF = dict(swing_lb=10, min_zone=100, max_zone=1200, min_away=500, zone_age=48,
           rsi_thr=20, rsi_win=3, wick_ratio=0.5, min_rng=0.8, sl_buf=1.5, max_sl=1500,
           tp_pts=600, adds=0, add_gap=150, trend=False, ema=200, sides="both",
           spread=0.30, max_per_zone=2,
           cf=None, cf_win=10, cf_add=False, m1_exit=False, m1_exit_min=300, m1_exit_wick=0.5)


def load_m1(path):
    d = pd.read_csv(path, parse_dates=["datetime"]).rename(columns={"datetime": "t"})
    return d[["t", "open", "high", "low", "close"]].sort_values("t").reset_index(drop=True)


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + up / dn)).fillna(50).values


def zones_h1(h1, c):
    """H1 pair-candle zones (same rules as the EA). returns list of dicts"""
    O, H, L, C = h1.open.values, h1.high.values, h1.low.values, h1.close.values
    out = []
    for k in range(c["swing_lb"] + 2, len(h1)):
        a, b = k - 1, k
        lo = a - c["swing_lb"]
        formed = h1.t.iloc[k] + pd.Timedelta(hours=1)
        if C[a] < O[a] and C[b] > O[b]:
            bot, top = min(L[a], L[b]), min(O[a], C[a], O[b], C[b])
            if L[lo:a].min() >= bot and P(c["min_zone"]) <= top - bot <= P(c["max_zone"]):
                out.append(dict(dir=1, top=top, bot=bot, formed=formed, k=k))
        if C[a] > O[a] and C[b] < O[b]:
            top, bot = max(H[a], H[b]), max(O[a], C[a], O[b], C[b])
            if H[lo:a].max() <= top and P(c["min_zone"]) <= top - bot <= P(c["max_zone"]):
                out.append(dict(dir=-1, top=top, bot=bot, formed=formed, k=k))
    if c.get("gap_zones"):
        for k in range(2, len(h1)):
            formed = h1.t.iloc[k] + pd.Timedelta(hours=1)
            if L[k] - H[k - 2] >= P(c.get("min_gap", 200)):
                out.append(dict(dir=1, top=L[k], bot=H[k - 2], formed=formed, k=k, gap=True))
            if L[k - 2] - H[k] >= P(c.get("min_gap", 200)):
                out.append(dict(dir=-1, top=L[k - 2], bot=H[k], formed=formed, k=k, gap=True))
        if c.get("gap_only"):
            out = [z for z in out if z.get("gap")]
        out.sort(key=lambda z: z["formed"])
    return out


def run(m1, cfg=None):
    c = {**DEF, **(cfg or {})}
    h1 = m1.set_index("t").resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
    ema = h1.close.ewm(span=c["ema"], adjust=False).mean()
    h1_close_at = dict(zip(h1.t + pd.Timedelta(hours=1), zip(h1.close.values, ema.values)))
    Z = zones_h1(h1, c)
    T = m1.t.values; O, H, L, C = (m1[x].values for x in ["open", "high", "low", "close"])
    R = rsi(m1.close)
    # M5 bars (for cf on M5): completes at M1 bar whose minute % 5 == 4
    m5 = m1.set_index("t").resample("5min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    m5c = {}
    prev = None
    for ts, r in m5.iterrows():
        if prev is not None:
            m5c[ts + pd.Timedelta(minutes=4)] = (r.open, r.high, r.low, r.close, prev.high, prev.low)
        prev = r
    pend = None                      # waiting for confirm
    zi, active, trades = 0, [], []
    pos = None                       # dict(d, legs=[entry,...], sl, tp, t, z)
    last_h1 = (None, None)
    for i in range(20, len(m1) - 1):
        t = pd.Timestamp(T[i])
        # new zones become active
        while zi < len(Z) and Z[zi]["formed"] <= t:
            z = dict(Z[zi]); z.update(away=False, trades=0, dead=False, ext=None, exp=z["formed"] + pd.Timedelta(hours=c["zone_age"]))
            active.append(z); zi += 1
        # H1 close events
        if t in h1_close_at:
            hc, he = h1_close_at[t]; last_h1 = (hc, he)
            for z in active:
                if (z["dir"] > 0 and hc < z["bot"]) or (z["dir"] < 0 and hc > z["top"]) or t >= z["exp"]:
                    z["dead"] = True
            active = [z for z in active if not z["dead"]]
        o, h, l, cl = O[i], H[i], L[i], C[i]
        # manage position on this bar
        if pos is not None:
            d = pos["d"]
            if (d > 0 and l <= pos["sl"]) or (d < 0 and h >= pos["sl"]):
                ex = pos["sl"] if (o - pos["sl"]) * d > 0 else o
                close(pos, ex, t, "SL", trades, c); pos = None
            elif (d > 0 and h >= pos["tp"]) or (d < 0 and l <= pos["tp"]):
                close(pos, pos["tp"], t, "TP", trades, c); pos = None
            elif c["m1_exit"] and (cl - pos["legs"][0]) * d >= P(c["m1_exit_min"]):
                rng_ = h - l
                cf_against = (cl < o and cl < L[i - 1]) if d > 0 else (cl > o and cl > H[i - 1])
                wick_against = rng_ > 0 and ((h - max(o, cl)) if d > 0 else (min(o, cl) - l)) >= c["m1_exit_wick"] * rng_
                if cf_against or wick_against:
                    close(pos, cl, t, "M1X", trades, c); pos = None
        # waiting for confirm
        if pend is not None and c["cf"]:
            z = pend["z"]; d = z["dir"]
            pend["ext"] = min(pend["ext"], l) if d > 0 else max(pend["ext"], h)
            sl = pend["ext"] - d * c["sl_buf"]
            ok = False
            if c["cf"] == "m1":
                ok = (cl > o and cl > pend["hi"]) if d > 0 else (cl < o and cl < pend["lo"])
            elif c["cf"] == "m5" and t in m5c:
                fo, fh, fl, fc, ph, pl = m5c[t]
                ok = (fc > fo and fc > ph) if d > 0 else (fc < fo and fc < pl)
            if ok:
                e = O[i + 1]
                if c["cf_add"] and pos is not None and pos["z"] is z:
                    pos["legs"].append(e)
                elif pos is None and abs(e - sl) <= P(c["max_sl"]) and (e - sl) * d > 0:
                    pos = dict(d=d, legs=[e], sl=sl, tp=e + d * P(c["tp_pts"]), t=pd.Timestamp(T[i + 1]), z=z)
                    z["trades"] += 1
                pend = None
            elif i >= pend["until"] or (d > 0 and l <= sl) or (d < 0 and h >= sl):
                pend = None

        # zone logic on closed bar i -> act at open of i+1
        for z in active:
            buy = z["dir"] > 0
            if c["sides"] == "buy" and not buy or c["sides"] == "sell" and buy:
                continue
            if not z["away"]:
                if (h - z["top"] if buy else z["bot"] - l) >= P(c["min_away"]):
                    z["away"] = True
                continue
            touch = (l <= z["top"]) if buy else (h >= z["bot"])
            if touch:
                z["ext"] = l if z["ext"] is None else (min(z["ext"], l) if buy else max(z["ext"], h))
            if z["ext"] is None:
                continue
            rng = h - l
            wick = (min(o, cl) - l) if buy else (h - max(o, cl))
            rs = R[i - c["rsi_win"] + 1:i + 1]
            os_ = rs.min() <= c["rsi_thr"] if buy else rs.max() >= 100 - c["rsi_thr"]
            wickoff = rng >= c["min_rng"] and wick >= c["wick_ratio"] * rng
            if not (os_ and wickoff):
                continue
            e = O[i + 1]
            if c["cf"] and not c["cf_add"]:
                if pos is None and pend is None:
                    pend = dict(z=z, hi=h, lo=l, ext=z["ext"], until=i + c["cf_win"])
                continue
            if c["cf"] and c["cf_add"] and pos is None and pend is None:
                pass  # first leg on wick below, then wait for cf to add
            if pos is None:
                if c["trend"] and last_h1[0] is not None and ((last_h1[0] < last_h1[1]) if buy else (last_h1[0] > last_h1[1])):
                    continue
                sl = (z["ext"] - c["sl_buf"]) if buy else (z["ext"] + c["sl_buf"])
                if abs(e - sl) > P(c["max_sl"]) or (e - sl) * z["dir"] <= 0:
                    continue
                pos = dict(d=z["dir"], legs=[e], sl=sl, tp=e + z["dir"] * P(c["tp_pts"]), t=pd.Timestamp(T[i + 1]), z=z)
                z["trades"] += 1
                if c["cf"] and c["cf_add"]:
                    pend = dict(z=z, hi=h, lo=l, ext=z["ext"], until=i + c["cf_win"])
            elif pos["z"] is z and len(pos["legs"]) <= c["adds"]:
                # add only after price moved against the last entry by add_gap and wicked again
                if (pos["legs"][-1] - e) * z["dir"] >= P(c["add_gap"]):
                    pos["legs"].append(e)
            if pos is not None and pos["z"] is z:
                pass
        for z in active:
            if z["trades"] >= c["max_per_zone"] and (pos is None or pos["z"] is not z):
                z["dead"] = True
        # after a closed round, zone must move away again
        if pos is None:
            for z in active:
                if z["ext"] is not None and z["trades"] > 0:
                    z["away"] = False; z["ext"] = None
        active = [z for z in active if not z["dead"]]
    return pd.DataFrame(trades)


def close(pos, price, t, why, trades, c):
    usd = sum((price - e) * pos["d"] - c["spread"] for e in pos["legs"])
    trades.append(dict(open_t=pos["t"], close_t=t, dir="BUY" if pos["d"] > 0 else "SELL", legs=len(pos["legs"]),
                       entry=round(pos["legs"][0], 2), sl=round(pos["sl"], 2), tp=round(pos["tp"], 2),
                       exit=round(price, 2), why=why, usd=round(usd, 2),
                       risk_pts=round(abs(pos["legs"][0] - pos["sl"]) / 0.01)))


def stats(tr):
    if tr.empty:
        return dict(n=0)
    eq = tr.usd.cumsum()
    dd = (eq - np.maximum.accumulate(np.r_[0, eq.values])[1:]).min()
    w, l_ = tr[tr.usd > 0].usd.sum(), -tr[tr.usd < 0].usd.sum()
    streak = max((sum(1 for _ in g) for k, g in itertools.groupby(tr.usd < 0) if k), default=0)
    return dict(n=len(tr), win=round((tr.usd > 0).mean() * 100, 1), net=round(tr.usd.sum(), 1),
                pf=round(w / l_, 2) if l_ else None, dd=round(dd, 1), avg_risk_pts=int(tr.risk_pts.mean()),
                streak=streak)


if __name__ == "__main__":
    m1 = load_m1(sys.argv[1])
    cfg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    tr = run(m1, cfg)
    print(json.dumps(stats(tr)))

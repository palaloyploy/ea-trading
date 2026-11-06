"""Compare well-known public XAUUSD strategy concepts on the same M15 data, same costs.
0.01 lot: $1 per $1 move. Spread 0.30$. Intrabar: SL checked before TP (conservative).
"""
import sys, json, itertools
import numpy as np, pandas as pd

sys.path.insert(0, "/home/claude")
import backtest as bt

SPREAD = 0.30


def prep(m):
    m = m.copy()
    ny = (m.t - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
    utc = ny.dt.tz_convert("UTC")
    m["uh"] = utc.dt.hour.fillna(-1).astype(int)
    m["uday"] = utc.dt.date
    return m


class Book:
    """one position at a time"""
    def __init__(s): s.pos = None; s.trades = []

    def open(s, t, d, entry, sl, tp, tag=""):
        if s.pos is None and (entry - sl) * d > 0:
            s.pos = dict(t=t, d=d, entry=entry, sl=sl, tp=tp, tag=tag)

    def step(s, t, o, h, l):
        p = s.pos
        if p is None:
            return
        d = p["d"]
        if (d > 0 and l <= p["sl"]) or (d < 0 and h >= p["sl"]):
            ex = p["sl"] if (o - p["sl"]) * d > 0 else o
            s.close(t, ex, "SL")
        elif p["tp"] is not None and ((d > 0 and h >= p["tp"]) or (d < 0 and l <= p["tp"])):
            s.close(t, p["tp"], "TP")

    def close(s, t, price, why):
        p = s.pos
        usd = (price - p["entry"]) * p["d"] - SPREAD
        s.trades.append(dict(open_t=p["t"], close_t=t, d=p["d"], usd=usd, why=why))
        s.pos = None


def stats(tr):
    tr = pd.DataFrame(tr)
    if tr.empty:
        return dict(n=0, net=0, win=0, pf=None, dd=0)
    eq = tr.usd.cumsum()
    dd = (eq - np.maximum.accumulate(np.r_[0, eq.values])[1:]).min()
    w, l = tr[tr.usd > 0].usd.sum(), -tr[tr.usd < 0].usd.sum()
    return dict(n=len(tr), net=round(tr.usd.sum(), 1), win=round((tr.usd > 0).mean() * 100, 1),
                pf=round(w / l, 2) if l else None, dd=round(dd, 1))


# ---------------------------------------------------------------- A: Asian range breakout (London)
def asian_breakout(m, rr=1.5, min_rng=3.0, max_rng=25.0, buf=0.5):
    b = Book()
    T, O, H, L, C, UH, UD = m.t.values, m.open.values, m.high.values, m.low.values, m.close.values, m.uh.values, m.uday.values
    cur, rh, rl, done, armed = None, -1e9, 1e9, False, False
    for i in range(len(m)):
        if UD[i] != cur:
            cur, rh, rl, done, armed = UD[i], -1e9, 1e9, False, False
        b.step(T[i], O[i], H[i], L[i])
        if b.pos is not None and UH[i] >= 20:
            b.close(T[i], C[i], "TIME")
        if 0 <= UH[i] < 7:
            rh, rl = max(rh, H[i]), min(rl, L[i]); continue
        rng = rh - rl
        if done or not (7 <= UH[i] < 12) or not (min_rng <= rng <= max_rng) or b.pos is not None:
            continue
        up, dn = rh + buf, rl - buf
        if H[i] >= up and L[i] <= dn:
            done = True; continue
        if H[i] >= up:
            e = max(O[i], up); b.open(T[i], 1, e, rl - buf, e + rr * (e - rl + buf), "A"); done = True
            b.step(T[i], e, H[i], L[i])
        elif L[i] <= dn:
            e = min(O[i], dn); b.open(T[i], -1, e, rh + buf, e - rr * (rh + buf - e), "A"); done = True
            b.step(T[i], e, H[i], L[i])
    return b.trades


# ---------------------------------------------------------------- B: liquidity sweep reversal
def sweep_reversal(m, lb=20, tp_lb=50, min_rr=1.5, buf=0.5):
    b = Book()
    T, O, H, L, C, UH = m.t.values, m.open.values, m.high.values, m.low.values, m.close.values, m.uh.values
    ema9 = m.close.ewm(span=9, adjust=False).mean().values
    tp_ = (m.high + m.low + m.close) / 3
    day = m.uday
    vwap = (tp_.groupby(day).cumsum() / tp_.groupby(day).cumcount().add(1)).values  # no volume -> typical-price mean
    pend = None
    for i in range(tp_lb + 1, len(m)):
        if pend:
            b.open(T[i], *pend); pend = None
        b.step(T[i], O[i], H[i], L[i])
        if b.pos is not None or not (8 <= UH[i] < 20):
            continue
        lo, hi = L[i - lb:i].min(), H[i - lb:i].max()
        if L[i] < lo and C[i] > lo and C[i] > ema9[i] and C[i] > vwap[i]:
            sl, tp = L[i] - buf, H[i - tp_lb:i].max()
            if (tp - C[i]) >= min_rr * (C[i] - sl):
                pend = (1, O[i + 1] if i + 1 < len(m) else C[i], sl, tp, "B")
        elif H[i] > hi and C[i] < hi and C[i] < ema9[i] and C[i] < vwap[i]:
            sl, tp = H[i] + buf, L[i - tp_lb:i].min()
            if (C[i] - tp) >= min_rr * (sl - C[i]):
                pend = (-1, O[i + 1] if i + 1 < len(m) else C[i], sl, tp, "B")
    return b.trades


# ---------------------------------------------------------------- C: EMA trend pullback
def ema_pullback(m, rr=2.0, buf=0.5):
    b = Book()
    T, O, H, L, C = m.t.values, m.open.values, m.high.values, m.low.values, m.close.values
    e20 = m.close.ewm(span=20, adjust=False).mean().values
    e50 = m.close.ewm(span=50, adjust=False).mean().values
    e800 = m.close.ewm(span=800, adjust=False).mean().values  # ~ H1 EMA200
    pend = None
    for i in range(60, len(m) - 1):
        if pend:
            b.open(T[i], *pend); pend = None
        b.step(T[i], O[i], H[i], L[i])
        if b.pos is not None:
            continue
        if C[i] > e800[i] and e20[i] > e50[i] and L[i] <= e20[i] and C[i] > e20[i] and C[i] > O[i]:
            sl = L[i - 4:i + 1].min() - buf; e = O[i + 1]
            pend = (1, e, sl, e + rr * (e - sl), "C")
        elif C[i] < e800[i] and e20[i] < e50[i] and H[i] >= e20[i] and C[i] < e20[i] and C[i] < O[i]:
            sl = H[i - 4:i + 1].max() + buf; e = O[i + 1]
            pend = (-1, e, sl, e - rr * (sl - e), "C")
    return b.trades


# ---------------------------------------------------------------- D: Donchian H1 breakout (trend following, trailing exit)
def donchian_h1(m, n_in=20, n_out=10, atr_k=2.0):
    h1 = m.set_index("t").resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
    T, O, H, L, C = h1.t.values, h1.open.values, h1.high.values, h1.low.values, h1.close.values
    tr = np.maximum.reduce([H - L, np.abs(H - np.r_[C[0], C[:-1]]), np.abs(L - np.r_[C[0], C[:-1]])])
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    b = Book(); pend = None
    for i in range(n_in + 1, len(h1) - 1):
        if pend:
            b.open(T[i], *pend); pend = None
        b.step(T[i], O[i], H[i], L[i])
        p = b.pos
        if p is not None:  # trailing exit on opposite channel
            if p["d"] > 0 and C[i] < L[i - n_out:i].min():
                b.close(T[i], C[i], "EXIT")
            elif p["d"] < 0 and C[i] > H[i - n_out:i].max():
                b.close(T[i], C[i], "EXIT")
            continue
        e = O[i + 1]
        if C[i] > H[i - n_in:i].max():
            pend = (1, e, e - atr_k * atr[i], None, "D")
        elif C[i] < L[i - n_in:i].min():
            pend = (-1, e, e + atr_k * atr[i], None, "D")
    return b.trades


# ---------------------------------------------------------------- E: ours
def ours(m, cfg):
    tr = bt.run(m, cfg)
    return [dict(usd=u) for u in tr.sort_values("close_t").usd.values] if len(tr) else []


if __name__ == "__main__":
    D = "/tmp/claude-0/data/BaseMax_XAUUSD-LSTM/XAU_15m_data.csv"
    P = {"2023": ("2023-01-01", "2024-01-01"), "2024": ("2024-01-01", "2025-01-01"), "2025": ("2025-01-01", "2025-10-01")}
    data = {y: prep(bt.load(D, a, b)) for y, (a, b) in P.items()}
    base = {"trend": True, "be": False, "max_cont": 1, "cont_body": 300, "fvg": True, "adx_min": 20, "round_tp": True}
    S = {
        "A Asian range breakout": asian_breakout,
        "B Liquidity sweep reversal": sweep_reversal,
        "C EMA trend pullback": ema_pullback,
        "D Donchian H1 trend": donchian_h1,
        "E ของเรา v1.5 (EMA50)": lambda m: ours(m, base),
        "F ของเรา + EMA200": lambda m: ours(m, {**base, "ema": 200}),
    }
    out = {}
    for name, f in S.items():
        row = {}
        for y, m in data.items():
            row[y] = stats(f(m))
        out[name] = row
        print(name, json.dumps(row, ensure_ascii=False), flush=True)
    bh = {y: round(m.close.iloc[-1] - m.close.iloc[0], 1) for y, m in data.items()}
    print("Buy&hold 0.01 lot", bh)
    json.dump(dict(results=out, buyhold=bh), open("/tmp/claude-0/compare.json", "w"), ensure_ascii=False, default=str)

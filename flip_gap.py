"""Two setups read off the user's/coach's screenshots (5 Nov 2026):
  FLIP : an M15 (or M5) swing level is broken by a strong candle; price comes back to it;
         a LIMIT waits at the level in the break direction (old support -> resistance).
  GAP  : an H1 3-bar Fair Value Gap; price drops back into it; LIMIT at the gap edge.
Same costs as the other tests: 0.01 lot = $1 per $1, spread $0.30, SL checked before TP.
"""
import sys, json
import numpy as np, pandas as pd

sys.path.insert(0, "/home/claude")
from compare_strategies import Book, stats

P = lambda x: x * 0.01


def ema_h1_filter(m, span=200):
    h1 = m.set_index("t").close.resample("1h").last().dropna()
    e = h1.ewm(span=span, adjust=False).mean()
    up = (h1 > e).shift(1)                      # last completed H1
    return up.reindex(m.t.dt.floor("h")).ffill().fillna(False).values.astype(bool), \
           (h1 < e).shift(1).reindex(m.t.dt.floor("h")).ffill().fillna(False).values.astype(bool)


def flip(m, piv=3, min_body=300, sl_pts=600, tp_pts=1000, expire=16, trend=True, round_tp=True):
    T, O, H, L, C = m.t.values, m.open.values, m.high.values, m.low.values, m.close.values
    bull_ok, bear_ok = ema_h1_filter(m)
    b = Book(); pend = None
    hi_piv, lo_piv = [], []                          # (price, idx)
    for i in range(2 * piv + 1, len(m) - 1):
        # fill / manage
        if pend is not None and b.pos is None:
            d, px = pend["d"], pend["px"]
            if (d > 0 and L[i] <= px) or (d < 0 and H[i] >= px):
                e = min(O[i], px) if d > 0 else max(O[i], px)
                b.open(T[i], d, e, e - d * P(sl_pts), cap(e, d, tp_pts, round_tp), "FLIP")
                pend = None
                sl_only(b, T[i], H[i], L[i])
                continue
            elif i > pend["exp"]:
                pend = None
        b.step(T[i], O[i], H[i], L[i])
        # confirmed pivot at i-piv
        k = i - piv
        if H[k] == H[k - piv:k + piv + 1].max():
            hi_piv.append([H[k], k])
        if L[k] == L[k - piv:k + piv + 1].min():
            lo_piv.append([L[k], k])
        hi_piv[:] = hi_piv[-6:]; lo_piv[:] = lo_piv[-6:]
        body = abs(C[i] - O[i])
        if b.pos is not None or pend is not None or body < P(min_body):
            continue
        # strong red candle closes below a swing low -> sell limit back at that low
        if C[i] < O[i]:
            for lv in sorted(lo_piv, key=lambda x: -x[0]):
                if O[i] > lv[0] > C[i] and (not trend or bear_ok[i]):
                    pend = dict(d=-1, px=lv[0], exp=i + expire); lo_piv.remove(lv); break
        elif C[i] > O[i]:
            for lv in sorted(hi_piv, key=lambda x: x[0]):
                if O[i] < lv[0] < C[i] and (not trend or bull_ok[i]):
                    pend = dict(d=1, px=lv[0], exp=i + expire); hi_piv.remove(lv); break
    return b.trades


def sl_only(b, t, h, l):
    """fill bar: we don't know the path, so only the stop can be hit (conservative), never the target"""
    p = b.pos
    if p is not None and ((p["d"] > 0 and l <= p["sl"]) or (p["d"] < 0 and h >= p["sl"])):
        b.close(t, p["sl"], "SL")


def cap(e, d, tp_pts, round_tp, step=20.0, gap=1.0):
    tp = e + d * P(tp_pts)
    if round_tp:
        lvl = (np.floor(e / step) + 1) * step if d > 0 else np.ceil(e / step - 1) * step
        if (lvl - e) * d < P(300):
            lvl += d * step
        c = lvl - d * gap
        if (c - tp) * d < 0:
            tp = c
    return tp


def h1_gap(m, min_gap=200, sl_buf=300, tp_pts=1000, expire_h=24, trend=True, round_tp=True, edge="near"):
    h1 = m.set_index("t").resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
    HH, HL = h1.high.values, h1.low.values
    gaps = []                                  # (ready_time, d, near, far, expire)
    for k in range(2, len(h1)):
        ready = h1.t[k] + pd.Timedelta(hours=1)
        if HL[k] - HH[k - 2] >= P(min_gap):        # bullish FVG: support
            gaps.append((ready, 1, HL[k], HH[k - 2], ready + pd.Timedelta(hours=expire_h)))
        if HL[k - 2] - HH[k] >= P(min_gap):        # bearish FVG: resistance
            gaps.append((ready, -1, HH[k], HL[k - 2], ready + pd.Timedelta(hours=expire_h)))
    T, O, H, L, C = m.t.values, m.open.values, m.high.values, m.low.values, m.close.values
    bull_ok, bear_ok = ema_h1_filter(m)
    b = Book(); gi = 0; live = []
    for i in range(len(m)):
        t = pd.Timestamp(T[i])
        while gi < len(gaps) and gaps[gi][0] <= t:
            live.append(list(gaps[gi])); gi += 1
        b.step(T[i], O[i], H[i], L[i])
        keep = []
        for g in live:
            ready, d, near, far, exp = g
            if t >= exp:
                continue
            px = near if edge == "near" else (near + far) / 2
            touched = (L[i] <= px) if d > 0 else (H[i] >= px)
            if touched and b.pos is None and (not trend or (bull_ok[i] if d > 0 else bear_ok[i])):
                e = min(O[i], px) if d > 0 else max(O[i], px)
                sl = far - d * P(sl_buf)
                b.open(T[i], d, e, sl, cap(e, d, tp_pts, round_tp), "GAP")
                sl_only(b, T[i], H[i], L[i])
                continue                       # gap used
            if touched:
                continue                       # touched while busy -> gap used up
            keep.append(g)
        live = keep
    return b.trades


if __name__ == "__main__":
    import backtest as bt
    D = "/tmp/claude-0/data/BaseMax_XAUUSD-LSTM/XAU_15m_data.csv"
    data = {y: bt.load(D, a, b) for y, (a, b) in {"2023": ("2023-01-01", "2024-01-01"), "2024": ("2024-01-01", "2025-01-01"), "2025": ("2025-01-01", "2025-10-01")}.items()}
    d = pd.read_csv("/tmp/claude-0/data/gdf/XAUUSD_15m.csv", parse_dates=["datetime"])
    sv = d.datetime.dt.tz_convert("America/New_York").dt.tz_localize(None) + pd.Timedelta(hours=7)
    data["2026"] = pd.DataFrame(dict(t=sv, open=d.open, high=d.high, low=d.low, close=d.close)).sort_values("t").reset_index(drop=True)
    V = [
        ("FLIP M15 Limit ที่แนวเดิม (กรองเทรน)", lambda m: flip(m)),
        ("FLIP M15 ไม่กรองเทรน", lambda m: flip(m, trend=False)),
        ("FLIP M15 แท่งทะลุ >=500 จุด", lambda m: flip(m, min_body=500)),
        ("FLIP M15 SL 1000", lambda m: flip(m, sl_pts=1000)),
        ("GAP H1 Limit ขอบ gap (กรองเทรน)", lambda m: h1_gap(m)),
        ("GAP H1 ไม่กรองเทรน", lambda m: h1_gap(m, trend=False)),
        ("GAP H1 Limit กลาง gap", lambda m: h1_gap(m, edge="mid")),
        ("GAP H1 gap >= 500 จุด", lambda m: h1_gap(m, min_gap=500)),
    ]
    for name, f in V:
        parts, tot, n, w, dd = [], 0, 0, 0, 0
        for y, m in data.items():
            s = stats(f(m)); tot += s["net"]; n += s["n"]; w += s["n"] * s["win"] / 100; dd = min(dd, s["dd"])
            parts.append(f"{y}:{s['net']:+.0f}")
        print(f"{name} | {' '.join(parts)} | รวม {tot:+.0f}$ {n} ไม้ ชนะ {w / max(n, 1) * 100:.0f}% DD {dd:.0f}", flush=True)

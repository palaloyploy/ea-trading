"""Learn where zone trades fail.

1) Build a dataset: every time price returns to an H1 pair-candle zone (EA rules) and an M15 cf candle
   (engulfs previous high/low in the zone's direction) appears within 6 h -> one candidate trade.
   Entry = next M15 open. Outcome = first of +TP / -SL (1000 pts each, SL checked first) within 24 h.
2) Features describing the situation at entry (trend, momentum, volatility, zone, time ...).
3) Train on 2023-2024, pick threshold on 2025, report on 2026 (never seen).
"""
import sys, json
import numpy as np, pandas as pd

sys.path.insert(0, "/home/claude")
import backtest as bt
import m1_trick as mt

P = lambda x: x * 0.01
TP_PTS, SL_PTS, SPREAD = 1000, 1000, 0.30
ATR_K = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0


def load_all():
    D = "/tmp/claude-0/data/BaseMax_XAUUSD-LSTM/XAU_15m_data.csv"
    a = bt.load(D, "2022-06-01", "2025-10-01")
    d = pd.read_csv("/tmp/claude-0/data/gdf/XAUUSD_15m.csv", parse_dates=["datetime"])
    sv = d.datetime.dt.tz_convert("America/New_York").dt.tz_localize(None) + pd.Timedelta(hours=7)
    b = pd.DataFrame(dict(t=sv, open=d.open, high=d.high, low=d.low, close=d.close))
    return pd.concat([a, b]).sort_values("t").drop_duplicates("t").reset_index(drop=True)


def rsi(s, n):
    d = s.diff(); u = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); v = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + u / v)).fillna(50)


def atr(df, n=14):
    tr = np.maximum.reduce([df.high - df.low, (df.high - df.close.shift()).abs(), (df.low - df.close.shift()).abs()])
    return pd.Series(tr, index=df.index).ewm(alpha=1 / n, adjust=False).mean()


def adx(df, n=14):
    up = df.high.diff(); dn = -df.low.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(df, n)
    pdi = 100 * pd.Series(pdm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    ndi = 100 * pd.Series(ndm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    return (100 * (pdi - ndi).abs() / (pdi + ndi)).ewm(alpha=1 / n, adjust=False).mean()


def h_frame(m, rule):
    return m.set_index("t").resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def build(m):
    m = m.reset_index(drop=True)
    T = m.t.values; O, H, L, C = (m[c].values for c in ["open", "high", "low", "close"])
    R14 = rsi(m.close, 14).values
    A15 = atr(m).values
    # higher-TF features, shifted so only COMPLETED bars are used, aligned to each M15 bar start
    h1 = h_frame(m, "1h"); h4 = h_frame(m, "4h")
    f1 = pd.DataFrame(index=h1.index)
    f1["ema200"] = h1.close.ewm(span=200, adjust=False).mean()
    f1["ema50"] = h1.close.ewm(span=50, adjust=False).mean()
    f1["h1c"] = h1.close
    r9 = rsi(h1.close, 9)
    f1["rmin"] = r9.rolling(10).min(); f1["rmax"] = r9.rolling(10).max(); f1["r9"] = r9
    f1["adx"] = adx(h1); f1["atr1"] = atr(h1)
    f1["slope50"] = f1.ema50.diff(5)
    f1 = f1.shift(1)                                  # value known at the start of the next H1 bar
    f4 = pd.DataFrame(index=h4.index)
    f4["e4"] = h4.close.ewm(span=50, adjust=False).mean(); f4["h4c"] = h4.close
    f4 = f4.shift(1)
    key1 = m.t.dt.floor("h"); key4 = m.t.dt.floor("4h")
    F1 = f1.reindex(key1).reset_index(drop=True); F4 = f4.reindex(key4).reset_index(drop=True)
    day = m.t.dt.floor("D")
    dly = m.groupby(day).agg(h=("high", "max"), l=("low", "min")).shift(1)
    PDH = day.map(dly.h).values; PDL = day.map(dly.l).values
    thai_h = ((m.t - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
              .dt.tz_convert("Asia/Bangkok").dt.hour.fillna(-1).astype(int).values)

    Z = mt.zones_h1(h1.reset_index(), mt.DEF)
    rows = []
    tvals = m.t.values
    for z in Z:
        d = z["dir"]
        i0 = np.searchsorted(tvals, np.datetime64(z["formed"]))
        iend = min(len(m), i0 + 4 * 48)
        if i0 >= iend - 2:
            continue
        seg = slice(i0, iend)
        away = np.where((H[seg] - z["top"] >= P(500)) if d > 0 else (z["bot"] - L[seg] >= P(500)))[0]
        if not len(away):
            continue
        ja = i0 + away[0]
        tch = np.where((L[ja:iend] <= z["top"]) if d > 0 else (H[ja:iend] >= z["bot"]))[0]
        if not len(tch):
            continue
        it = ja + tch[0]
        # zone already broken by an H1 close?  (use M15 close at H1 boundaries as proxy)
        closes = C[i0:it]
        if len(closes) and ((closes.min() < z["bot"] - P(100)) if d > 0 else (closes.max() > z["top"] + P(100))):
            continue
        if it <= ja:
            continue
        away_pts = ((H[ja:it].max() - z["top"]) if d > 0 else (z["bot"] - L[ja:it].min())) / 0.01
        # first cf within 6 h
        for k in range(it, min(it + 24, len(m) - 2)):
            if (d > 0 and C[k] > O[k] and C[k] > H[k - 1]) or (d < 0 and C[k] < O[k] and C[k] < L[k - 1]):
                break
        else:
            continue
        ie = k + 1
        e = O[ie]
        ext = L[it:ie].min() if d > 0 else H[it:ie].max()
        # outcome
        f_ = F1.iloc[ie]
        if ATR_K and not np.isnan(f_.atr1):
            sl, tp = e - d * ATR_K * f_.atr1, e + d * ATR_K * f_.atr1
        else:
            sl, tp = e - d * P(SL_PTS), e + d * P(TP_PTS)
        res = 0
        for q in range(ie, min(ie + 96, len(m))):
            if (d > 0 and L[q] <= sl) or (d < 0 and H[q] >= sl):
                res = -1; break
            if (d > 0 and H[q] >= tp) or (d < 0 and L[q] <= tp):
                res = 1; break
        if res == 0:
            continue                              # neither within 24 h -> skip (rare)
        f, g = F1.iloc[ie], F4.iloc[ie]
        if f.isna().any() or g.isna().any() or np.isnan(PDH[ie]):
            continue
        a15 = A15[k]; a1 = f.atr1
        body = abs(C[k] - O[k]); rng = H[k] - L[k]
        wick = ((min(O[k], C[k]) - L[k]) if d > 0 else (H[k] - max(O[k], C[k]))) / rng if rng > 0 else 0
        step = 20.0
        lvl = (np.floor(e / step) + 1) * step if d > 0 else np.ceil(e / step - 1) * step
        rows.append(dict(
            t=pd.Timestamp(T[ie]), dir=d, win=int(res == 1),
            trend_ema200=d * (f.h1c - f.ema200) / a1,            # + = with trend
            trend_h4=d * (g.h4c - g.e4) / a1,
            slope50=d * f.slope50 / a1,
            rsi_regime=(f.rmin - 40) if d > 0 else (60 - f.rmax),  # + = Cardwell range agrees
            rsi9_h1=d * (f.r9 - 50),
            rsi14_m15=d * (R14[k] - 50),
            rsi_depth=(R14[it:ie].min() if d > 0 else 100 - R14[it:ie].max()),
            adx=f.adx,
            vol_ratio=a15 / a1,
            atr_h1_pts=a1 / 0.01,
            zone_h_pts=(z["top"] - z["bot"]) / 0.01,
            zone_age_h=(T[it] - np.datetime64(z["formed"])) / np.timedelta64(1, "h"),
            away_pts=away_pts,
            pierce_pts=((z["top"] - ext) if d > 0 else (ext - z["bot"])) / 0.01,
            through_zone=int((ext < z["bot"]) if d > 0 else (ext > z["top"])),
            wait_bars=ie - it,
            chase_pts=((e - z["top"]) if d > 0 else (z["bot"] - e)) / 0.01,
            cf_body_atr=body / a15,
            cf_wick=wick,
            room_round_pts=(lvl - e) * d / 0.01,
            pd_room=((PDH[ie] - e) if d > 0 else (e - PDL[ie])) / 0.01,
            hour_th=thai_h[ie], dow=pd.Timestamp(T[ie]).dayofweek,
        ))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    m = load_all()
    ds = build(m)
    ds.to_csv(f"/tmp/claude-0/zone_dataset{'_atr'+str(ATR_K) if ATR_K else ''}.csv", index=False)
    print(len(ds), "trades; base win", round(ds.win.mean() * 100, 1), "%")
    print(ds.groupby(ds.t.dt.year).win.agg(["size", "mean"]).round(3))

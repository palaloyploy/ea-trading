"""Event study: what happens after a "cf" (confirmation candle) on each timeframe at an H1 pair-candle zone.

For every H1 pair zone (EA rules) that price leaves (>=500 pts) and later comes back to touch:
  for each TF in M1/M5/M15/M30/H1, find the FIRST cf candle after the touch (within 6 h):
      Buy zone : green candle that closes above the previous candle's high
      Sell zone: red candle that closes below the previous candle's low
  entry = next bar open on that TF, SL = beyond the lowest/highest price since touch + 150 pts,
  then walk the price path bar by bar (base TF) to see what is hit first:
      TP = +tp pts, SL as above; time-out after 8 h -> close at market.
Also records: how far price already ran from the zone at entry, SL size, MFE/MAE.
"""
import sys, json
import numpy as np, pandas as pd

sys.path.insert(0, "/home/claude")
import m1_trick as mt

P = lambda x: x * 0.01
SPREAD = 0.30


def resample(base, rule):
    return base.set_index("t").resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()


def study(base, base_min, tfs, tp=900, buf=150, watch_h=6, hold_h=8, extra=None):
    """base: OHLC at base resolution (M1 or M15). tfs: dict name->minutes (multiples of base_min)."""
    h1 = resample(base, "1h")
    Z = mt.zones_h1(h1, mt.DEF)
    bars = {k: resample(base, f"{v}min") for k, v in tfs.items()}
    bt_ = base.t.values; bo, bh, bl, bc = (base[c].values for c in ["open", "high", "low", "close"])
    rows = []
    for z in Z:
        d = z["dir"]
        # path after zone forms
        i0 = np.searchsorted(bt_, np.datetime64(z["formed"]))
        end = np.searchsorted(bt_, np.datetime64(z["formed"] + pd.Timedelta(hours=48)))
        if i0 >= end:
            continue
        seg_h, seg_l, seg_c = bh[i0:end], bl[i0:end], bc[i0:end]
        # moved away
        away = np.where((seg_h - z["top"] >= P(500)) if d > 0 else (z["bot"] - seg_l >= P(500)))[0]
        if not len(away):
            continue
        j = away[0]
        touch = np.where((seg_l[j:] <= z["top"]) if d > 0 else (seg_h[j:] >= z["bot"]))[0]
        if not len(touch):
            continue
        it = i0 + j + touch[0]                                  # base index of first touch
        # zone broken by H1 close before touch? skip
        t_touch = pd.Timestamp(bt_[it])
        hb = h1[(h1.t + pd.Timedelta(hours=1) > z["formed"]) & (h1.t + pd.Timedelta(hours=1) <= t_touch)]
        if len(hb) and ((hb.close < z["bot"]).any() if d > 0 else (hb.close > z["top"]).any()):
            continue
        for name, df in bars.items():
            tfm = tfs[name]
            # first cf candle on this TF that STARTS at/after the touch bar start (floored) and closes within watch_h
            t0 = t_touch.floor(f"{tfm}min")
            k0 = np.searchsorted(df.t.values, np.datetime64(t0))
            k_end = np.searchsorted(df.t.values, np.datetime64(t_touch + pd.Timedelta(hours=watch_h)))
            hit = None
            for k in range(max(k0, 1), min(k_end, len(df) - 1)):
                o, h, l, c = df.open[k], df.high[k], df.low[k], df.close[k]
                ph, pl = df.high[k - 1], df.low[k - 1]
                if (d > 0 and c > o and c > ph) or (d < 0 and c < o and c < pl):
                    hit = k; break
            if hit is None:
                rows.append(dict(tf=name, zone=str(z["formed"]), dir=d, cf=False)); continue
            t_entry = df.t[hit] + pd.Timedelta(minutes=tfm)          # next bar open time
            ie = np.searchsorted(bt_, np.datetime64(t_entry))
            if ie >= len(base):
                continue
            entry = bo[ie]
            ext = bl[it:ie].min() if d > 0 else bh[it:ie].max()
            sl = ext - P(buf) if d > 0 else ext + P(buf)
            risk = (entry - sl) * d
            if risk <= 0:
                continue
            tpp = entry + d * P(tp)
            iend = np.searchsorted(bt_, np.datetime64(t_entry + pd.Timedelta(hours=hold_h)))
            res, exitp = "TIME", None
            mfe = mae = 0.0
            for q in range(ie, min(iend, len(base))):
                fav = (bh[q] - entry) if d > 0 else (entry - bl[q])
                adv = (entry - bl[q]) if d > 0 else (bh[q] - entry)
                mae = max(mae, adv)
                if adv >= risk:
                    res, exitp = "SL", sl; break
                mfe = max(mfe, fav)
                if fav >= P(tp):
                    res, exitp = "TP", tpp; break
            if exitp is None:
                exitp = bc[min(iend, len(base)) - 1]
            usd = (exitp - entry) * d - SPREAD
            ran = ((entry - z["top"]) if d > 0 else (z["bot"] - entry)) / 0.01
            rows.append(dict(tf=name, zone=str(z["formed"]), dir=d, cf=True, t_entry=t_entry, t_touch=t_touch, wait_min=(t_entry - t_touch).total_seconds() / 60,
                             ran_pts=ran, risk_pts=risk / 0.01, res=res, usd=usd, R=usd / risk,
                             mfe_pts=mfe / 0.01, mae_pts=mae / 0.01))
    return pd.DataFrame(rows)


def add_filters(df, base):
    h1 = resample(base, "1h")
    ema = h1.close.ewm(span=200, adjust=False).mean()
    dd = h1.close.diff(); u = dd.clip(lower=0).ewm(alpha=1 / 9, adjust=False).mean(); v = (-dd.clip(upper=0)).ewm(alpha=1 / 9, adjust=False).mean()
    rsi = 100 - 100 / (1 + u / v)
    f = pd.DataFrame(dict(t=h1.t + pd.Timedelta(hours=1), up=(h1.close > ema).values, dn=(h1.close < ema).values,
                          rmin=rsi.rolling(10).min().values, rmax=rsi.rolling(10).max().values))
    df = df.copy()
    c = df[df.cf == True].sort_values("t_entry")
    m = pd.merge_asof(c[["t_entry"]].reset_index(), f.sort_values("t"), left_on="t_entry", right_on="t", direction="backward").set_index("index")
    df["trend_ok"] = pd.Series(dtype=object); df["rsi_ok"] = pd.Series(dtype=object)
    df.loc[m.index, "trend_ok"] = np.where(df.loc[m.index, "dir"] > 0, m.up, m.dn)
    df.loc[m.index, "rsi_ok"] = np.where(df.loc[m.index, "dir"] > 0, m.rmin >= 40, m.rmax <= 60)
    # M1 RSI(14) extreme between touch and entry (coach's trick) -- only meaningful on M1 data
    b = base.set_index("t").close
    r1 = mt.rsi(b.reset_index(drop=True))
    rs = pd.Series(r1, index=b.index)
    ext = []
    for _, row in df.loc[m.index].iterrows():
        w = rs[row.t_touch - pd.Timedelta(minutes=5): row.t_entry]
        ext.append((w.min() <= 25) if row.dir > 0 else (w.max() >= 75))
    df["rsi_ext"] = pd.Series(dtype=object)
    df.loc[m.index, "rsi_ext"] = pd.Series(ext, index=m.index, dtype=object)
    return df


def summarize(df, order):
    out = []
    for tf in order:
        g = df[df.tf == tf]
        if not len(g):
            continue
        c = g[g.cf == True]
        out.append(dict(TF=tf, zones=len(g), cf_rate=round(len(c) / len(g) * 100), trades=len(c),
                        wait_min=int(c.wait_min.median()) if len(c) else None,
                        ran_pts=int(c.ran_pts.median()) if len(c) else None,
                        sl_pts=int(c.risk_pts.median()) if len(c) else None,
                        tp_rate=round((c.res == "TP").mean() * 100) if len(c) else None,
                        sl_rate=round((c.res == "SL").mean() * 100) if len(c) else None,
                        net_usd=round(c.usd.sum(), 1), avg_R=round(c.R.mean(), 2) if len(c) else None,
                        mfe_med=int(c.mfe_pts.median()) if len(c) else None))
    return pd.DataFrame(out)


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "m1":
        base = mt.load_m1("/tmp/claude-0/data/Sai310421_xauusd-data/csv/XAUUSD/XAUUSD_M1_2026Q1Q2.csv")
        tfs = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60}
        df = study(base, 1, tfs)
    else:
        import backtest as bt
        D = "/tmp/claude-0/data/BaseMax_XAUUSD-LSTM/XAU_15m_data.csv"
        parts = [bt.load(D, "2023-01-01", "2025-10-01")]
        d = pd.read_csv("/tmp/claude-0/data/gdf/XAUUSD_15m.csv", parse_dates=["datetime"])
        t = d.datetime.dt.tz_convert("UTC").dt.tz_localize(None)
        parts.append(pd.DataFrame(dict(t=t, open=d.open, high=d.high, low=d.low, close=d.close)))
        base = pd.concat(parts).sort_values("t").drop_duplicates("t").reset_index(drop=True)
        tfs = {"M15": 15, "M30": 30, "H1": 60}
        df = study(base, 15, tfs)
    df = add_filters(df, base)
    df.to_csv(f"/tmp/claude-0/tfstudy_{mode}.csv", index=False)
    print(summarize(df, list(tfs)).to_string(index=False))

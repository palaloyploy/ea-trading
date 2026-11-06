"""Bar-by-bar replica of WickFill_H1Pair_EA.mq5 (ENTRY_ENGULF + continuation + opposite-zone guard)
on M15 gold data. Conservative intrabar rules: if SL and TP are both inside one M15 bar, SL wins;
a limit-fill bar may hit SL in the same bar but never TP.
"""
import sys, json, itertools
import pandas as pd, numpy as np

P = lambda x: x * 0.01  # จุด -> $

DEF = dict(
    swing_lb=10, min_zone=100, max_zone=1200, min_away=500, zone_age=48, max_per_zone=2,
    max_chase=1500, limit_exp=4, sl_mode="fixed", sl_pts=1000, sl_buf=50, tp_pts=1000,
    be=True, be_trig=500, be_off=20, spread=30, max_day=4, max_open=2,
    cont=True, max_cont=3, avoid=True, min_room=500, tp_before=50, level_age=120,
    usd_per_pt=0.01, start_bal=100.0, trend=False, ema=50, only=0,
    brk=True, brk_watch=6, brk_buf=100, main=True,
    rsi_ext=0, rsi_ext_len=14, rsi_entry=0, bias=None, ztf=1, ztf_extra=False,
    exit_pair=0, exit_profit=0, exit_tp_far=0,
    vbc=False, vbc_k=2.0, vbc_fib=0.5, vbc_buf=100, vbc_exp=8, vbc_main=True,
    rsi_reg=0, rsi_len=9, rsi_lb=10, rsi_mode='and',
    flip=False, flip_watch=12, flip_buf=100, flip_trend=True, flip_chase=600,
    session=None, adx_min=0, cont_body=0, fvg=False, fvg_lb=6,
    sweep=None, sweep_lb=32, round_tp=False, round_step=20.0, round_gap=1.0,
    sl_pct=0.0, tp_pct=0.0, partial=False, tp2_mult=2.0, min_rr=0.0,
)


def load(path, start, end):
    df = pd.read_csv(path, sep=";")
    df["t"] = pd.to_datetime(df["Date"], format="%Y.%m.%d %H:%M")
    df = df.sort_values("t").drop_duplicates("t")
    df = df[(df.t >= start) & (df.t < end)].reset_index(drop=True)
    return df[["t", "Open", "High", "Low", "Close"]].rename(columns=str.lower)


def run(m15, cfg=None):
    c = {**DEF, **(cfg or {})}
    h1 = (m15.set_index("t").resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
          .dropna().reset_index())
    h1c = (h1.t + pd.Timedelta(hours=1)).tolist()
    HO, HH, HL, HC = h1.open.values, h1.high.values, h1.low.values, h1.close.values
    def _zt(hrs):
        hz = (m15.set_index("t").resample(f"{hrs}h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index())
        return hz, (hz.t + pd.Timedelta(hours=hrs)).tolist()
    ZTF = [c["ztf"]] if not c["ztf_extra"] else [1, c["ztf"]]
    ZD = {hrs: _zt(hrs) for hrs in ZTF}
    def _col(rule):
        f = m15.set_index("t").resample(rule).agg({"open": "first", "close": "last"}).dropna()
        col = np.sign(f.close - f.open).shift(1)          # last COMPLETED candle colour
        return col.reindex(m15.t.dt.floor(rule)).fillna(0).values
    BIAS_D = _col("1D") if c["bias"] else None
    BIAS_H4 = _col("4h") if c["bias"] else None
    zp = {hrs: 0 for hrs in ZTF}
    EMA = h1.close.ewm(span=c["ema"], adjust=False).mean().values
    _d = h1.close.diff(); _u = _d.clip(lower=0).ewm(alpha=1 / c["rsi_len"], adjust=False).mean(); _v = (-_d.clip(upper=0)).ewm(alpha=1 / c["rsi_len"], adjust=False).mean()
    RSIH = (100 - 100 / (1 + _u / _v)).fillna(50)
    RMIN = RSIH.rolling(c["rsi_lb"]).min().values; RMAX = RSIH.rolling(c["rsi_lb"]).max().values
    # ADX(14) on H1 (Wilder) - sideway filter
    up_m = h1.high.diff(); dn_m = -h1.low.diff()
    pdm = np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0); ndm = np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0)
    tr_ = np.maximum.reduce([h1.high - h1.low, (h1.high - h1.close.shift()).abs(), (h1.low - h1.close.shift()).abs()])
    a = 1 / 14
    atr = pd.Series(tr_).ewm(alpha=a, adjust=False).mean()
    pdi = 100 * pd.Series(pdm).ewm(alpha=a, adjust=False).mean() / atr
    ndi = 100 * pd.Series(ndm).ewm(alpha=a, adjust=False).mean() / atr
    ADX = (100 * (pdi - ndi).abs() / (pdi + ndi)).ewm(alpha=a, adjust=False).mean().fillna(0).values
    # Thai hour: server = New York + 7h  ->  Thai = UTC + 7
    ny = (m15.t - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
    THAI_H = ny.dt.tz_convert("Asia/Bangkok").dt.hour.fillna(-1).astype(int).values
    day = m15.t.dt.floor("D")
    dly = m15.groupby(day).agg(h=("high", "max"), l=("low", "min"))
    prev = dly.shift(1)
    PDH = day.map(prev.h).values; PDL = day.map(prev.l).values
    last_h1 = [-1]
    T = [pd.Timestamp(x) for x in m15.t.values]
    BAR = pd.Timedelta(minutes=c.get("bar_min", 15))
    O, H, L, C = m15.open.values, m15.high.values, m15.low.values, m15.close.values
    n = len(m15)
    _d2 = m15.close.diff(); _u2 = _d2.clip(lower=0).ewm(alpha=1 / c["rsi_ext_len"], adjust=False).mean(); _v2 = (-_d2.clip(upper=0)).ewm(alpha=1 / c["rsi_ext_len"], adjust=False).mean()
    RS = (100 - 100 / (1 + _u2 / _v2)).fillna(50).values
    _tr15 = np.maximum.reduce([m15.high - m15.low, (m15.high - m15.close.shift()).abs(), (m15.low - m15.close.shift()).abs()])
    ATR15 = pd.Series(_tr15).ewm(alpha=1 / 14, adjust=False).mean().shift(1).bfill().values
    PAIRX = {}
    if c["exit_pair"]:
        _mx = m15.set_index("t").resample(f"{c['exit_pair']}min").agg({"open": "first", "close": "last"}).dropna()
        _o, _c = _mx.open.values, _mx.close.values
        for k in range(1, len(_mx)):
            ct = _mx.index[k] + pd.Timedelta(minutes=c["exit_pair"])
            if _c[k - 1] > _o[k - 1] and _c[k] < _o[k]:
                PAIRX[ct] = -1          # green -> red pair: exit longs
            elif _c[k - 1] < _o[k - 1] and _c[k] > _o[k]:
                PAIRX[ct] = 1           # red -> green pair: exit shorts
    zones, levels, positions, pendings, trades = [], [], [], [], []
    filled_day = {}
    h1p = 0
    flips = []
    up = dict(until=None, lvl=0, sw=0.0, ref=0.0, done=True)
    dn = dict(until=None, lvl=0, sw=0.0, ref=0.0, done=True)

    def detect(k, hrs):
        hz, hzc = ZD[hrs]
        HO, HH, HL, HC = hz.open.values, hz.high.values, hz.low.values, hz.close.values
        if k < 1:
            return
        a, b = k - 1, k
        lo = max(0, a - c["swing_lb"])
        formed = hzc[k]
        if HC[a] < HO[a] and HC[b] > HO[b]:
            bot = min(HL[a], HL[b]); top = min(HO[a], HC[a], HO[b], HC[b])
            ok = a == lo or HL[lo:a].min() >= bot
            if ok and P(c["min_zone"]) <= top - bot <= P(c["max_zone"]):
                add(1, top, bot, formed, (HH[b] - top) >= P(c["min_away"]))
        if HC[a] > HO[a] and HC[b] < HO[b]:
            top = max(HH[a], HH[b]); bot = max(HO[a], HC[a], HO[b], HC[b])
            ok = a == lo or HH[lo:a].max() <= top
            if ok and P(c["min_zone"]) <= top - bot <= P(c["max_zone"]):
                add(-1, top, bot, formed, (bot - HL[b]) >= P(c["min_away"]))

    def add(d, top, bot, formed, away):
        levels.append(dict(dir=d, top=top, bot=bot, formed=formed,
                           exp=formed + pd.Timedelta(hours=c["level_age"]), broken=False))
        zones.append(dict(dir=d, top=top, bot=bot, formed=formed, exp=formed + pd.Timedelta(hours=c["zone_age"]),
                          away=away, touched=False, ext=None, trades=0, dead=False,
                          cont=False, cc=0, cstop=0.0))

    def obstacle(d, entry):
        best = None
        for lv in levels:
            if lv["broken"] or lv["dir"] != -d:
                continue
            if lv["bot"] <= entry <= lv["top"]:
                return entry
            if d > 0 and lv["bot"] > entry and (best is None or lv["bot"] < best):
                best = lv["bot"]
            if d < 0 and lv["top"] < entry and (best is None or lv["top"] > best):
                best = lv["top"]
        return best

    def build(d, entry, sl, is_cont):
        if c["sl_mode"] == "fixed" and not is_cont:
            sl = entry - d * (entry * c["sl_pct"] / 100 if c["sl_pct"] else P(c["sl_pts"]))
        if (d > 0 and sl >= entry) or (d < 0 and sl <= entry):
            return None
        tp = entry + d * (entry * c["tp_pct"] / 100 if c["tp_pct"] else P(c["exit_tp_far"] or c["tp_pts"]))
        if c["round_tp"]:
            st = c["round_step"]
            lvl = (np.floor(entry / st) + 1) * st if d > 0 else np.ceil(entry / st - 1) * st
            if (lvl - entry) * d < P(300):
                lvl += d * st
            cap = lvl - d * c["round_gap"]
            if (cap - tp) * d < 0:
                tp = cap
        if c["avoid"]:
            ob = obstacle(d, entry)
            if ob is not None:
                if (ob - entry) * d < P(c["min_room"]):
                    return None
                cap = ob - d * P(c["tp_before"])
                if (cap - tp) * d < 0:
                    tp = cap
        if c["min_rr"] and (tp - entry) * d < c["min_rr"] * (entry - sl) * d:
            return None
        return sl, tp

    def trend_ok(d, i=None):
        if c["only"] and d != c["only"]:
            return False
        if c["bias"] and i is not None:
            if c["bias"] in ("d", "both") and BIAS_D[i] != d:
                return False
            if c["bias"] in ("h4", "both") and BIAS_H4[i] != d:
                return False
            if c["bias"] == "either" and BIAS_D[i] != d and BIAS_H4[i] != d:
                return False
        if c["session"] and i is not None:
            hh = THAI_H[i + 1] if i + 1 < n else THAI_H[i]
            if not (c["session"][0] <= hh < c["session"][1]):
                return False
        if c["adx_min"] and last_h1[0] >= 0 and ADX[last_h1[0]] < c["adx_min"]:
            return False
        if last_h1[0] < 0:
            return True
        k = last_h1[0]
        ema_ok = (HC[k] > EMA[k]) if d > 0 else (HC[k] < EMA[k])
        if c["rsi_reg"]:
            # Cardwell range rule: bull regime = RSI holds above 40, bear regime = RSI stays below 60
            rsi_ok = (RMIN[k] >= c["rsi_reg"]) if d > 0 else (RMAX[k] <= 100 - c["rsi_reg"])
            if not c["trend"]:
                return rsi_ok
            return (ema_ok and rsi_ok) if c["rsi_mode"] == "and" else (ema_ok or rsi_ok)
        return ema_ok if c["trend"] else True

    def find_fvg(i, d, ref):
        """nearest unfilled 3-bar Fair Value Gap between current close and the wick-tip entry"""
        best = None
        for j in range(i, max(1, i - c["fvg_lb"]), -1):
            if d > 0 and L[j] > H[j - 2]:
                edge = L[j]
                if ref < edge < C[i] and (j == i or L[j + 1:i + 1].min() > edge) and (best is None or edge > best):
                    best = edge
            if d < 0 and H[j] < L[j - 2]:
                edge = H[j]
                if C[i] < edge < ref and (j == i or H[j + 1:i + 1].max() < edge) and (best is None or edge < best):
                    best = edge
        return best

    def can_trade(t):
        return len([q for q in positions if q.get("leg") != 2]) + len(pendings) < c["max_open"] and filled_day.get(t.date(), 0) < c["max_day"]

    def place(i, z, price, sl, is_cont):
        for p in [p for p in pendings if p["z"] is z]:
            pendings.remove(p)
        d = z["dir"]
        if not can_trade(T[i]) or (not z.get("notrend") and not trend_ok(d, i)):
            return False

        if (C[i] > price) if d > 0 else (C[i] < price):
            if build(d, price, sl, is_cont) is None:
                return False
            pendings.append(dict(z=z, d=d, price=price, sl=sl, cont=is_cont, age=0, market=False))
        else:  # already at the wick tip -> market at next open
            pendings.append(dict(z=z, d=d, price=None, sl=sl, cont=is_cont, age=0, market=True))
        pendings[-1]["kind"] = z.get("kind", "ADD" if is_cont else "FIRST")
        return True

    def fill(i, p, price):
        d = p["d"]
        b = build(d, price, p["sl"], p["cont"])
        if b is None:
            return
        sl, tp = b
        pos = dict(d=d, entry=price, sl=sl, sl0=sl, tp=tp, t=T[i], be=False, cont=p["cont"], kind=p["kind"], w=1.0)
        if c["partial"]:
            pos["w"] = 0.5
            run = dict(pos); run["tp"] = price + d * c["tp2_mult"] * abs(tp - price); run["leg"] = 2
            pos["leg"] = 1; pos["mate"] = run
            positions.append(run)
        positions.append(pos)
        filled_day[T[i].date()] = filled_day.get(T[i].date(), 0) + 1
        z = p["z"]
        if not p["cont"]:
            z["trades"] += 1; z["away"] = False; z["touched"] = False
        if (d > 0 and L[i] <= sl) or (d < 0 and H[i] >= sl):
            for q in [q for q in positions if q["t"] == T[i] and q["entry"] == price]:
                close(i, q, sl, "SL")

    def close(i, pos, price, why):
        if why == "TP" and pos.get("leg") == 1 and pos["mate"] in positions:
            pos["mate"]["sl"] = pos["entry"] + pos["d"] * P(c["be_off"]); pos["mate"]["be"] = True
        pts = ((price - pos["entry"]) / 0.01 * pos["d"] - c["spread"]) * pos.get("w", 1.0)
        trades.append(dict(open_t=pos["t"], close_t=T[i], dir="BUY" if pos["d"] > 0 else "SELL",
                           kind=pos["kind"], entry=round(pos["entry"], 2),
                           sl=round(pos["sl0"], 2), tp=round(pos["tp"], 2), exit=round(price, 2), reason=why,
                           pts=round(pts, 1), usd=round(pts * c["usd_per_pt"], 2)))
        positions.remove(pos)

    for i in range(n):
        # 1) positions opened earlier: SL / TP / BE on bar i
        for pos in list(positions):
            d = pos["d"]
            if (d > 0 and L[i] <= pos["sl"]) or (d < 0 and H[i] >= pos["sl"]):
                ex = pos["sl"]
                if (O[i] - ex) * d < 0:
                    ex = O[i]
                close(i, pos, ex, "BE" if pos["be"] else "SL")
            elif (d > 0 and H[i] >= pos["tp"]) or (d < 0 and L[i] <= pos["tp"]):
                close(i, pos, pos["tp"], "TP")
            elif c["be"] and not pos["be"] and ((H[i] - pos["entry"]) if d > 0 else (pos["entry"] - L[i])) >= P(c["be_trig"]):
                pos["sl"] = pos["entry"] + d * P(c["be_off"]); pos["be"] = True
            elif c["exit_pair"] and PAIRX.get(T[i] + BAR) == -d and (C[i] - pos["entry"]) * d >= P(c["exit_profit"]):
                close(i, pos, C[i], "PAIR")
        # 2) pending fills on bar i
        for p in list(pendings):
            if p["z"]["dead"]:
                pendings.remove(p); continue
            if p["market"]:
                pendings.remove(p); fill(i, p, O[i]); continue
            d = p["d"]
            if (L[i] <= p["price"]) if d > 0 else (H[i] >= p["price"]):
                pendings.remove(p)
                fill(i, p, min(O[i], p["price"]) if d > 0 else max(O[i], p["price"]))

        # 3) bar closed -> H1 updates first
        bclose = T[i] + BAR
        while h1p < len(h1) and h1c[h1p] <= bclose:
            last_h1[0] = h1p
            h1p += 1
        for hrs in ZTF:
          hz, hzc = ZD[hrs]
          while zp[hrs] < len(hz) and hzc[zp[hrs]] <= bclose:
            hc = hz.close.values[zp[hrs]]
            for z in zones:
                if not z["dead"] and ((z["dir"] > 0 and hc < z["bot"]) or (z["dir"] < 0 and hc > z["top"]) or bclose >= z["exp"]):
                    z["dead"] = True
            for lv in levels:
                if lv["broken"]:
                    continue
                if c["flip"] and ((lv["dir"] < 0 and hc > lv["top"]) or (lv["dir"] > 0 and hc < lv["bot"])):
                    flips.append(dict(dir=-lv["dir"], top=lv["top"], bot=lv["bot"], until=bclose + pd.Timedelta(hours=c["flip_watch"]),
                                      touched=False, dead=False, cont=False, kind="FLIP", notrend=not c["flip_trend"]))
                if lv["dir"] < 0 and hc > lv["top"]:
                    lv["broken"] = True
                    up.update(until=bclose + pd.Timedelta(hours=c["brk_watch"]), lvl=lv["top"], sw=0.0, ref=0.0, done=False)
                if lv["dir"] > 0 and hc < lv["bot"]:
                    lv["broken"] = True
                    dn.update(until=bclose + pd.Timedelta(hours=c["brk_watch"]), lvl=lv["bot"], sw=0.0, ref=0.0, done=False)
            detect(zp[hrs], hrs)
            zp[hrs] += 1
        levels[:] = [lv for lv in levels if not lv["broken"] and bclose < lv["exp"]]
        for p in [p for p in pendings if p["z"]["dead"]]:
            pendings.remove(p)
        zones[:] = [z for z in zones if not z["dead"]]

        # 4) pending: price hasn't come back yet -> new 3-bar FVG closer to price? move the limit there
        if c["fvg"] and i >= 2:
            for p in pendings:
                if p["market"]:
                    continue
                if p["d"] > 0 and L[i] > H[i - 2] and p["price"] < L[i] < C[i]:
                    p["price"] = L[i]; p["fvg"] = True
                if p["d"] < 0 and H[i] < L[i - 2] and C[i] < H[i] < p["price"]:
                    p["price"] = H[i]; p["fvg"] = True
        # 4b) pending expiry
        for p in list(pendings):
            if not p["market"]:
                p["age"] += 1
                if p["age"] >= p.get("exp_override", c["limit_exp"]):
                    pendings.remove(p)
                    if not p["z"]["cont"]:
                        p["z"]["touched"] = False
        if i == 0 or i + 1 >= n:
            continue
        o, h, l, cl = O[i], H[i], L[i], C[i]
        pO, pH, pL, pC = O[i - 1], H[i - 1], L[i - 1], C[i - 1]

        # 4b) after an H1 zone breaks: fade the top / bottom on M15
        if c["brk"]:
            bc = T[i] + BAR
            if not up["done"] and bc < up["until"]:
                if cl > o and h >= up["sw"] and h > up["lvl"]:
                    up["sw"], up["ref"] = h, l
                elif up["ref"] > 0:
                    up["sw"] = max(up["sw"], h)
                    if cl < o and cl < up["ref"]:
                        zb = dict(dir=-1, dead=False, cont=False, kind="BRK")
                        place(i, zb, up["ref"], up["sw"] + P(c["brk_buf"]), True); up["done"] = True
            if not dn["done"] and bc < dn["until"]:
                if cl < o and (dn["sw"] == 0 or l <= dn["sw"]) and l < dn["lvl"]:
                    dn["sw"], dn["ref"] = l, h
                elif dn["ref"] > 0:
                    dn["sw"] = min(dn["sw"], l)
                    if cl > o and cl > dn["ref"]:
                        zb = dict(dir=1, dead=False, cont=False, kind="BRK")
                        place(i, zb, dn["ref"], dn["sw"] - P(c["brk_buf"]), True); dn["done"] = True

        # 4d) VBC: very big candle (body >= k x ATR) -> limit at its fib retracement, SL beyond the candle
        if c["vbc"] and abs(cl - o) >= c["vbc_k"] * ATR15[i]:
            d = 1 if cl > o else -1
            px = h - c["vbc_fib"] * (h - l) if d > 0 else l + c["vbc_fib"] * (h - l)
            sl = l - P(c["vbc_buf"]) if d > 0 else h + P(c["vbc_buf"])
            zv = dict(dir=d, dead=False, cont=False, kind="VBC")
            if not any(p_["kind"] == "VBC" for p_ in pendings):
                place(i, zv, px, sl, True)
                if pendings and pendings[-1]["z"] is zv:
                    pendings[-1]["exp_override"] = c["vbc_exp"]

        # 4c) S/R flip: broken zone -> price comes back to it -> M15 cf away from it -> enter with the break
        if c["flip"]:
            bc = T[i] + BAR
            for f in flips:
                if f["dead"]:
                    continue
                if bc >= f["until"]:
                    f["dead"] = True; continue
                d = f["dir"]
                # zone fails again (closes back through the far side) -> drop
                if (d > 0 and cl < f["bot"]) or (d < 0 and cl > f["top"]):
                    f["dead"] = True; continue
                if (d > 0 and l <= f["top"]) or (d < 0 and h >= f["bot"]):
                    f["touched"] = True
                if not f["touched"]:
                    continue
                cf = (cl > o and cl > pH) if d > 0 else (cl < o and cl < pL)
                near = (cl - f["top"] <= P(c["flip_chase"])) if d > 0 else (f["bot"] - cl <= P(c["flip_chase"]))
                if cf and near:
                    sl = f["bot"] - P(c["flip_buf"]) if d > 0 else f["top"] + P(c["flip_buf"])
                    place(i, f, pH if d > 0 else pL, sl, True)
                    f["used"] = True
            flips[:] = [f for f in flips if not f["dead"] and not f.get("used")]

        # 5) zone logic
        for z in (zones if c["main"] and c["vbc_main"] else []):
            has_pend = any(p["z"] is z for p in pendings)
            if not z["cont"] and not has_pend and z["trades"] >= c["max_per_zone"]:
                z["dead"] = True; continue
            if T[i] < z["formed"]:
                continue
            buy = z["dir"] > 0
            if z["cont"]:
                if (cl < z["cstop"]) if buy else (cl > z["cstop"]):
                    z["cont"] = False; z["touched"] = False; continue
                same = (pC > pO) if buy else (pC < pO)
                sig = (cl > o and cl > pH) if buy else (cl < o and cl < pL)
                big = abs(cl - o) >= P(c["cont_body"])
                if same and sig and big and z["cc"] < c["max_cont"]:
                    sl = l - P(c["sl_buf"]) if buy else h + P(c["sl_buf"])
                    if place(i, z, pH if buy else pL, sl, True):
                        z["cc"] += 1; z["cstop"] = l if buy else h
                continue
            if not z["away"]:
                if (h - z["top"] if buy else z["bot"] - l) >= P(c["min_away"]):
                    z["away"] = True
                continue
            if has_pend:
                continue
            if (l <= z["top"]) if buy else (h >= z["bot"]):
                if not z["touched"]:
                    z["ext"] = l if buy else h
                    z["ti"] = i
                z["touched"] = True
            if not z["touched"]:
                continue
            if (cl - z["top"] if buy else z["bot"] - cl) > P(c["max_chase"]):
                z["touched"] = False; continue
            if not ((cl > o and cl > pH) if buy else (cl < o and cl < pL)):
                continue
            if c["rsi_entry"] and ((RS[i] > 50 - c["rsi_entry"]) if buy else (RS[i] < 50 + c["rsi_entry"])):
                continue
            if c["rsi_ext"]:
                w = RS[max(0, z["ti"] - 1):i + 1]
                if not ((w.min() <= c["rsi_ext"]) if buy else (w.max() >= 100 - c["rsi_ext"])):
                    continue
            if c["sweep"]:
                ext = min(z["ext"], l) if buy else max(z["ext"], h)
                ok = False
                if c["sweep"] in ("swing", "both"):
                    a = max(0, z["ti"] - c["sweep_lb"]); b = max(a + 1, z["ti"] - 2)
                    ref = L[a:b].min() if buy else H[a:b].max()
                    ok = ok or ((ext < ref) if buy else (ext > ref))
                if c["sweep"] in ("pdl", "both") and not np.isnan(PDL[i]):
                    ok = ok or ((ext < PDL[i]) if buy else (ext > PDH[i]))
                if not ok:
                    z["touched"] = False
                    continue
            if c["sl_mode"] == "candle":
                sl = l - P(c["sl_buf"]) if buy else h + P(c["sl_buf"])
            elif c["sl_mode"] == "zone":
                sl = z["bot"] - P(c["sl_buf"]) if buy else z["top"] + P(c["sl_buf"])
            else:
                sl = (pH - P(c["sl_pts"])) if buy else (pL + P(c["sl_pts"]))
            if place(i, z, pH if buy else pL, sl, False):
                z["cont"] = c["cont"]; z["cc"] = 0; z["cstop"] = l if buy else h
        zones[:] = [z for z in zones if not z["dead"]]

    for pos in list(positions):
        close(n - 1, pos, C[n - 1], "END")
    return pd.DataFrame(trades)


def stats(tr, start_bal=100.0):
    if tr.empty:
        return dict(trades=0)
    tr = tr.sort_values("close_t")
    eq = start_bal + tr.usd.cumsum()
    peak = np.maximum.accumulate(np.r_[start_bal, eq.values])[1:]
    wins, loss = tr[tr.usd > 0], tr[tr.usd < 0]
    streak = max((sum(1 for _ in g) for k, g in itertools.groupby(tr.usd < 0) if k), default=0)
    return dict(
        trades=len(tr), first=int((tr.kind == "FIRST").sum()), adds=int((tr.kind == "ADD").sum()),
        brk=int((tr.kind == "BRK").sum()), flip=int((tr.kind == "FLIP").sum()), vbc=int((tr.kind == "VBC").sum()),
        win_rate=round(len(wins) / len(tr) * 100, 1),
        tp=int((tr.reason == "TP").sum()), sl=int((tr.reason == "SL").sum()), be=int((tr.reason == "BE").sum()),
        net_pts=round(tr.pts.sum()), net_usd=round(tr.usd.sum(), 2),
        pf=round(wins.usd.sum() / -loss.usd.sum(), 2) if len(loss) else None,
        avg_win=round(wins.usd.mean(), 2) if len(wins) else 0, avg_loss=round(loss.usd.mean(), 2) if len(loss) else 0,
        max_dd_usd=round((eq - peak).min(), 2), min_equity=round(eq.min(), 2), final=round(eq.iloc[-1], 2),
        max_losing_streak=streak,
    )


if __name__ == "__main__":
    path, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    cfg = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
    tr = run(load(path, start, end), cfg)
    print(json.dumps(stats(tr), default=str))
    if len(sys.argv) > 5:
        tr.to_csv(sys.argv[5], index=False)

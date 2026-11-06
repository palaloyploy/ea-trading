"""Plot XAUUSD M15 around the coach's EP.11 example (25 Sep 2026, times UTC+7)
with H1 pair-candle zones, the coach's trades (read off his screenshots, approximate)
and the trades our EA logic takes on the same bars."""
import sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Rectangle

sys.path.insert(0, "/home/claude")
import backtest as bt
import m1_trick as mt

fm.fontManager.addfont("/usr/share/fonts/opentype/tlwg/Loma.otf")
fm.fontManager.addfont("/usr/share/fonts/opentype/tlwg/Loma-Bold.otf")
plt.rcParams["font.family"] = "Loma"

SRC = sys.argv[1]
OUT = sys.argv[2]
d = pd.read_csv(SRC, parse_dates=["datetime"])
utc = d.datetime.dt.tz_convert("UTC")
# server time used by the EA simulator = New York + 7
server = utc.dt.tz_convert("America/New_York").dt.tz_localize(None) + pd.Timedelta(hours=7)
m15 = pd.DataFrame(dict(t=server, open=d.open, high=d.high, low=d.low, close=d.close)).sort_values("t").reset_index(drop=True)
th = utc.dt.tz_convert("Asia/Bangkok").dt.tz_localize(None)
OFF = (th - server).iloc[-1]                # server -> Thai offset for this period

# ---- our EA (main module, v1.6 settings) on all data, then keep the window
cfg = {"trend": True, "be": False, "max_cont": 1, "cont_body": 300, "fvg": True, "adx_min": 20, "round_tp": True, "ema": 200}
tr = bt.run(m15, cfg)
cfg_nf = {}                                  # clip rules only, no filters
tr_nf = bt.run(m15, cfg_nf)

# ---- window in Thai time
w0, w1 = pd.Timestamp("2026-09-25 06:00"), pd.Timestamp("2026-09-26 03:30")
x = m15.assign(t=m15.t + OFF)
x = x[(x.t >= w0) & (x.t <= w1)].reset_index(drop=True)

# ---- H1 zones (EA rules) from all data, keep those alive in window
h1 = m15.set_index("t").resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
Z = mt.zones_h1(h1, mt.DEF)
zones = []
for z in Z:
    f = z["formed"] + OFF
    if f > w1 or f < w0 - pd.Timedelta(hours=30):
        continue
    after = h1[(h1.t + OFF + pd.Timedelta(hours=1) > f)]
    end = w1
    for _, r in after.iterrows():
        if (z["dir"] > 0 and r.close < z["bot"]) or (z["dir"] < 0 and r.close > z["top"]):
            end = r.t + OFF + pd.Timedelta(hours=1); break
    if end > w0 and z["bot"] < x.high.max() + 5 and z["top"] > x.low.min() - 5:
        zones.append((f - pd.Timedelta(hours=2), end, z))

# ---- coach's trades read off his EP.11 screenshots (approximate)
coach = [
    dict(t="2026-09-25 18:15", d=-1, e=4309.0, sl=4316.0, tp=4296.0, lab="โค้ช Sell ที่ยอด"),
    dict(t="2026-09-25 21:45", d=1, e=4271.0, sl=4262.0, tp=4283.0, lab="โค้ช Buy ปลายไส้แดง"),
    dict(t="2026-09-25 22:15", d=1, e=4273.0, sl=4269.5, tp=4285.0, lab="โค้ช Buy ไล่เทรน"),
]

# ---- figure
INK, MUTED, GRID = "#1f2328", "#6e7781", "#e6e8eb"
UP, DN = "#2e8b57", "#c0392b"
fig, ax = plt.subplots(figsize=(16, 8.5), dpi=130)
fig.patch.set_facecolor("white"); ax.set_facecolor("white")
idx = {t: i for i, t in enumerate(x.t)}
def xi(t):
    t = pd.Timestamp(t)
    return np.searchsorted(x.t.values, np.datetime64(t)) if t >= x.t.iloc[0] else 0

for zs, ze, z in zones:
    a, b = xi(zs), xi(ze)
    col = UP if z["dir"] > 0 else DN
    ax.add_patch(Rectangle((a - 0.5, z["bot"]), max(b - a, 1), z["top"] - z["bot"], color=col, alpha=0.13, lw=0))
    ax.text(a, z["top"] if z["dir"] < 0 else z["bot"], ("แนวต้าน H1 " if z["dir"] < 0 else "แนวรับ H1 ") + f"{z['bot']:.0f}-{z['top']:.0f}",
            fontsize=8, color=MUTED, va="bottom" if z["dir"] < 0 else "top")

for i, r in x.iterrows():
    col = UP if r.close >= r.open else DN
    ax.vlines(i, r.low, r.high, color=col, lw=0.9)
    ax.add_patch(Rectangle((i - 0.32, min(r.open, r.close)), 0.64, max(abs(r.close - r.open), 0.05), color=col, lw=0))

def draw_trade(t, d, e, sl, tp, lab, style, color, yoff):
    i = xi(t)
    ax.hlines([sl], i, i + 6, colors=DN, lw=1.2, linestyles=style)
    ax.hlines([tp], i, i + 6, colors=UP, lw=1.2, linestyles=style)
    ax.plot([i], [e], marker="^" if d > 0 else "v", ms=11, color=color, mec="white", mew=1.2, zorder=5)
    ax.annotate(lab, (i, e), xytext=(8, yoff), textcoords="offset points", fontsize=9, color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))

for k, c in enumerate(coach):
    draw_trade(c["t"], c["d"], c["e"], c["sl"], c["tp"], c["lab"], "--", "#1f6feb", 22 if k % 2 == 0 else -26)

def ea_rows(t_df, tag):
    if t_df.empty:
        return []
    t_df = t_df.assign(o=pd.to_datetime(t_df.open_t) + OFF, c=pd.to_datetime(t_df.close_t) + OFF)
    return t_df[(t_df.o >= w0) & (t_df.o <= w1)].assign(tag=tag)

rows = pd.concat([ea_rows(tr, "EA v1.6"), ea_rows(tr_nf, "กติกาคลิปล้วน")], ignore_index=True) if len(tr) or len(tr_nf) else pd.DataFrame()
for k, r in rows.iterrows():
    color = "#8250df" if r.tag == "EA v1.6" else "#bf8700"
    res = f"{r.reason} {r.usd:+.1f}$"
    draw_trade(r.o, 1 if r.dir == "BUY" else -1, r.entry, r.sl, r.tp, f"{r.tag} {r.dir} = {res}", ":", color, -40 - 14 * (k % 3))

ticks = [i for i, t in enumerate(x.t) if t.minute == 0 and t.hour % 2 == 0]
ax.set_xticks(ticks); ax.set_xticklabels([x.t[i].strftime("%d/%m %H:%M") for i in ticks], rotation=0, fontsize=8, color=MUTED)
ax.tick_params(axis="y", labelsize=9, colors=MUTED)
ax.grid(axis="y", color=GRID, lw=0.6); ax.set_axisbelow(True)
for s in ["top", "right"]:
    ax.spines[s].set_visible(False)
for s in ["left", "bottom"]:
    ax.spines[s].set_color(GRID)
ax.set_xlim(-1, len(x) + 2)
ax.set_ylim(x.low.min() - 6, x.high.max() + 6)
ax.set_title("ทองคำ M15 วันที่ 25 ก.ย. 2026 (เวลาไทย): จุดเข้าของโค้ช (EP.11) เทียบกับ EA", fontsize=14, color=INK, loc="left", fontweight="bold", pad=28)
fig.text(0.012, 0.935, "สามเหลี่ยมน้ำเงิน = โค้ช (อ่านจากรูป ราคาโดยประมาณ)   ม่วง = EA v1.6   เหลือง = กติกาคลิปล้วนไม่มีตัวกรอง   เส้นแดง = SL  เส้นเขียว = TP   กล่องจาง = โซนแท่งคู่ H1 ที่ EA ตี",
        fontsize=9, color=MUTED)
fig.tight_layout(rect=(0, 0, 1, 0.93))
fig.savefig(OUT)
print("zones", len(zones), "EA trades in window:")
print(rows[["tag", "o", "dir", "entry", "sl", "tp", "exit", "reason", "usd"]].to_string() if len(rows) else "none")
print("price range", x.low.min(), x.high.max())

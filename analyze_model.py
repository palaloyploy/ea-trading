import sys, json
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

ds = pd.read_csv("/tmp/claude-0/zone_dataset.csv", parse_dates=["t"])
FEAT = [c for c in ds.columns if c not in ("t", "win")]
tr = ds[ds.t < "2025-01-01"]; va = ds[(ds.t >= "2025-01-01") & (ds.t < "2026-01-01")]; te = ds[ds.t >= "2026-01-01"]
usd = lambda w: np.where(w == 1, 9.7, -10.3)

print("== 1. แต่ละปัจจัย: % ชนะ ในกลุ่มต่ำ/กลาง/สูง (train 2022-24 | test 2025-26)")
rows = []
for f in FEAT:
    if f in ("dir", "through_zone", "dow"):
        cats = sorted(ds[f].unique())
        for cv in cats:
            a = tr[tr[f] == cv].win; b = pd.concat([va, te])[lambda x: x[f] == cv].win
            rows.append((f, str(cv), len(a), a.mean(), len(b), b.mean()))
        continue
    q = tr[f].quantile([1 / 3, 2 / 3]).values
    for lab, lo, hi in [("ต่ำ", -np.inf, q[0]), ("กลาง", q[0], q[1]), ("สูง", q[1], np.inf)]:
        a = tr[(tr[f] > lo) & (tr[f] <= hi)].win
        o = pd.concat([va, te]); b = o[(o[f] > lo) & (o[f] <= hi)].win
        rows.append((f, f"{lab} ({lo:.1f}..{hi:.1f})", len(a), a.mean(), len(b), b.mean()))
t = pd.DataFrame(rows, columns=["feature", "bucket", "n_train", "win_train", "n_test", "win_test"])
# keep features whose best/worst bucket differ by >=8% in BOTH periods in the same direction
keep = []
for f, g in t.groupby("feature", sort=False):
    sp_tr = g.win_train.max() - g.win_train.min()
    best = g.win_train.idxmax(); worst = g.win_train.idxmin()
    consistent = g.loc[best, "win_test"] > g.loc[worst, "win_test"]
    if sp_tr >= 0.08 and consistent:
        keep.append(f)
pd.set_option("display.width", 200)
print(t[t.feature.isin(keep)].round(3).to_string(index=False))
print("ปัจจัยที่แยกแพ้/ชนะได้ทั้งสองช่วง:", keep)

print("\n== 2. โมเดล (train 2022-24, เลือกเกณฑ์ด้วย 2025, ทดสอบจริง 2026)")
X, y = tr[FEAT], tr.win
models = {
    "logistic": make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000)),
    "boosting": HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, min_samples_leaf=30, l2_regularization=1.0),
}
out = {}
for name, mdl in models.items():
    mdl.fit(X, y)
    pv, pt = mdl.predict_proba(va[FEAT])[:, 1], mdl.predict_proba(te[FEAT])[:, 1]
    auc_v, auc_t = roc_auc_score(va.win, pv), roc_auc_score(te.win, pt)
    # choose threshold on 2025 maximizing $ with >=30 trades
    best = None
    for th in np.arange(0.40, 0.70, 0.01):
        s = pv >= th
        if s.sum() < 30:
            continue
        v = usd(va.win.values[s]).sum()
        if best is None or v > best[1]:
            best = (th, v)
    th = best[0]
    s = pt >= th
    res = dict(auc_2025=round(auc_v, 3), auc_2026=round(auc_t, 3), threshold=round(th, 2),
               all_2026=dict(n=len(te), win=round(te.win.mean() * 100, 1), usd=round(usd(te.win.values).sum(), 1)),
               picked_2026=dict(n=int(s.sum()), win=round(te.win.values[s].mean() * 100, 1) if s.sum() else None,
                                usd=round(usd(te.win.values[s]).sum(), 1)))
    out[name] = res
    print(name, json.dumps(res, ensure_ascii=False))
    if name == "logistic":
        coef = pd.Series(mdl[-1].coef_[0], index=FEAT).sort_values()
        print("น้ำหนักปัจจัย (บวก=ช่วยให้ชนะ):"); print(coef.round(3).to_string())

print("\n== 3. กฎง่าย ๆ (เทียบ)")
def rule(df, cond, lab):
    s = cond(df)
    print(f"{lab}: {s.sum()} ไม้ ชนะ {df.win[s].mean()*100:.1f}% ${usd(df.win.values[s]).sum():+.0f}")
for name, df in [("train 2022-24", tr), ("2025", va), ("2026", te)]:
    print("--", name)
    rule(df, lambda d: d.win >= 0, "ทั้งหมด")
    rule(df, lambda d: d.trend_ema200 > 0, "ตามเทรน EMA200")
    rule(df, lambda d: (d.trend_ema200 > 0) & (d.trend_h4 > 0), "ตามเทรน EMA200 + H4")

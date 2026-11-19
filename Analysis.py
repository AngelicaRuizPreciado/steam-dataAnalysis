"""
Step 6: segments and controls.

Input:   data/steam.db (views from step 5) and sql/segments.sql
Output:  data/processed/segment_summary.csv        medians per activity segment
         data/processed/within_age_band.csv        segment medians inside each age band
         data/processed/partial_correlations.csv   raw vs age/size-controlled Spearman

Run:  python 06_analysis.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

DB = Path("data/steam.db")
OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)

PROGRESSION = ["ach_retention_ratio", "ach_tail_ratio", "ach_share_under_1pct", "review_pct_positive"]

with sqlite3.connect(DB) as con:
    con.executescript(Path("sql/segments.sql").read_text(encoding="utf-8"))
    df = pd.read_sql("SELECT * FROM analysis_base", con)

df["log_owners"] = np.log10(df["owners_low"].clip(lower=1))
print(f"Games: {len(df)} | low-signal (progression excluded): {df['low_signal_achievements'].sum()}")

# ---------------------------------------------------- 1. activity segments
agg = {c: "median" for c in PROGRESSION + ["age_days", "owners_low", "posts_12m"]}
seg = df.groupby("activity_segment").agg(n=("appid", "size"), **{k: (k, v) for k, v in agg.items()})
seg.round(3).to_csv(OUT / "segment_summary.csv")
print("\n--- Medians by activity segment ---")
print(seg.round(3).to_string())

print("\n--- Kruskal-Wallis across segments (are the groups different?) ---")
for m in PROGRESSION:
    groups = [g[m].dropna() for _, g in df.groupby("activity_segment")]
    if all(len(g) > 1 for g in groups):
        h, p = stats.kruskal(*groups)
        print(f"{m:24s} H={h:6.2f}  p={p:.3f}")

# ------------------------------------------- 2. same comparison within age bands
within = (df.groupby(["age_band", "activity_segment"])
            .agg(n=("appid", "size"), retention=("ach_retention_ratio", "median"),
                 share_under_1pct=("ach_share_under_1pct", "median"),
                 review_pct=("review_pct_positive", "median"))
            .round(3))
within.to_csv(OUT / "within_age_band.csv")
print("\n--- Segment medians within age bands (1 = youngest) ---")
print(within.to_string())

# -------------------------- 3. raw vs partial Spearman (controls: age, owners)
def partial_spearman(d: pd.DataFrame, x: str, y: str, controls: list[str]):
    d = d[[x, y] + controls].dropna()
    r = d.rank()
    Z = np.column_stack([np.ones(len(r))] + [r[c] for c in controls])
    res = {v: r[v].to_numpy() - Z @ np.linalg.lstsq(Z, r[v].to_numpy(), rcond=None)[0] for v in (x, y)}
    rho = np.corrcoef(res[x], res[y])[0, 1]
    dof = len(d) - 2 - len(controls)
    t = rho * np.sqrt(dof / (1 - rho**2))
    return rho, 2 * stats.t.sf(abs(t), dof), len(d)

rows = []
for m in PROGRESSION:
    d = df[["posts_per_month", m, "age_days", "log_owners"]].dropna()
    raw, p_raw = stats.spearmanr(d["posts_per_month"], d[m])
    part, p_part, n = partial_spearman(df, "posts_per_month", m, ["age_days", "log_owners"])
    rows.append({"metric": m, "n": n, "rho_raw": raw, "p_raw": p_raw, "rho_controlled": part, "p_controlled": p_part})
pc = pd.DataFrame(rows).round(3)
pc.to_csv(OUT / "partial_correlations.csv", index=False)
print("\n--- posts_per_month vs outcomes: raw vs controlling for age and owners ---")
print(pc.to_string(index=False))
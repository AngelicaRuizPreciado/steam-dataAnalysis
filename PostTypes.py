"""
Step 7: classify news posts by keyword rules and test the "mechanical" explanation.

Idea: content updates add achievements (lowering retention ratios by construction);
sales/events/announcements do not. If only update posts relate to low retention,
the mechanical explanation is supported.

Input:   data/steam.db (steps 5-6)
Output:  table news_types in data/steam.db
         data/processed/post_type_correlations.csv

Run:  python 07_post_types.py
"""
import re
import sqlite3
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

DB = Path("data/steam.db")
OUT = Path("data/processed")

# Order matters: the first matching rule wins. Edit the patterns freely and rerun.
RULES = [
    ("sale",   r"\bsale\b|discount|\d+\s?% off|\bbundles?\b|\bdeals?\b|free weekend|\bdlc\b|soundtrack|\bdemo\b"),
    ("update", r"patch|hotfix|hot fix|\bupdate|changelog|release notes|\bv?\d+\.\d+|\bfix(es|ed)?\b|\bbuild\b|version|\bbeta\b|roadmap|更新|日志|new (inventory|feature|content|mode|map)|skill tree"),
    ("event",  r"event|festival|\bfest\b|giveaway|contest|season|holiday|halloween|christmas|anniversary|winter|summer|spring|autumn|easter"),
]

def classify(title: str) -> str:
    t = (title or "").lower()
    for label, pattern in RULES:
        if re.search(pattern, t):
            return label
    return "other"

with sqlite3.connect(DB) as con:
    con.executescript(Path("sql/segments.sql").read_text(encoding="utf-8"))   # makes sure analysis_base exists
    news = pd.read_sql("SELECT appid, gid, title, date_unix FROM news GROUP BY appid, gid", con)
    news["post_type"] = news["title"].map(classify)
    news[["appid", "gid", "post_type"]].to_sql("news_types", con, if_exists="replace", index=False)

    window_start = int(time.time()) - 365 * 86400
    counts = pd.read_sql(
        """
        SELECT b.appid, b.age_days, b.owners_low,
               b.ach_retention_ratio, b.ach_tail_ratio, b.ach_share_under_1pct,
               SUM(t.post_type = 'update') AS n_update,
               SUM(t.post_type = 'event')  AS n_event,
               SUM(t.post_type = 'sale')   AS n_sale,
               SUM(t.post_type = 'other')  AS n_other
        FROM analysis_base b
        LEFT JOIN news n       ON n.appid = b.appid AND n.date_unix >= ?
        LEFT JOIN news_types t ON t.appid = n.appid AND t.gid = n.gid
        GROUP BY b.appid
        """,
        con, params=(window_start,),
    )

# ------------------------------------------------------------ sanity checks
share = news["post_type"].value_counts(normalize=True).round(3)
print("Share of all posts by type:\n" + share.to_string())
print("\nRandom sample of titles labelled 'other' (check the rules are not missing obvious patterns):")
print(news.loc[news["post_type"] == "other", "title"].sample(12, random_state=1).to_string(index=False))

# ------------------------------------------------------------- correlations
counts[["n_update", "n_event", "n_sale", "n_other"]] = counts[["n_update", "n_event", "n_sale", "n_other"]].fillna(0)
counts["log_owners"] = np.log10(counts["owners_low"].clip(lower=1))

def partial_spearman(d, x, y, controls):
    d = d[[x, y] + controls].dropna()
    r = d.rank()
    Z = np.column_stack([np.ones(len(r))] + [r[c] for c in controls])
    res = {v: r[v].to_numpy() - Z @ np.linalg.lstsq(Z, r[v].to_numpy(), rcond=None)[0] for v in (x, y)}
    rho = np.corrcoef(res[x], res[y])[0, 1]
    dof = len(d) - 2 - len(controls)
    t = rho * np.sqrt(dof / (1 - rho**2))
    return rho, 2 * stats.t.sf(abs(t), dof), len(d)

rows = []
for x in ["n_update", "n_event", "n_sale", "n_other"]:
    for y in ["ach_retention_ratio", "ach_tail_ratio", "ach_share_under_1pct"]:
        d = counts[[x, y]].dropna()
        raw, p_raw = stats.spearmanr(d[x], d[y])
        part, p_part, n = partial_spearman(counts, x, y, ["age_days", "log_owners"])
        rows.append({"post_type": x, "outcome": y, "n": n, "rho_raw": raw, "p_raw": p_raw,
                     "rho_controlled": part, "p_controlled": p_part})
res = pd.DataFrame(rows).round(3)
OUT.mkdir(parents=True, exist_ok=True)
res.to_csv(OUT / "post_type_correlations.csv", index=False)
print("\n--- Posts in the last 12 months by type vs progression (controls: age, owners) ---")
print(res.to_string(index=False))
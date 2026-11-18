"""
Step 4: build one row per game with progression and communication metrics.

Input:   data/interim/sample.csv, achievements.csv, news.csv
Output:  data/processed/game_metrics.csv

Run:  python 04_build_metrics.py
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

SAMPLE = Path("data/interim/sample.csv")
ACH = Path("data/interim/achievements.csv")
NEWS = Path("data/interim/news.csv")
OUT_DIR = Path("data/processed")
OUT_DIR.mkdir(parents=True, exist_ok=True)

NEWS_COUNT_CAP = 200   # must match step 3
WINDOW_DAYS = 365

today = pd.Timestamp.now(tz="UTC").normalize()
window_start = today - pd.Timedelta(days=WINDOW_DAYS)

# ---------------------------------------------------------------- progression
ach = pd.read_csv(ACH)
grp = ach.groupby("appid")["percent"]
ach_m = pd.DataFrame({
    "n_achievements_api": grp.size(),
    "ach_top_pct": grp.max(),                       # share unlocking the most common achievement
    "ach_median_pct": grp.median(),
    "ach_p10_pct": grp.quantile(0.10),              # rarity of the late-game tail
    "ach_share_under_1pct": grp.apply(lambda s: (s < 1).mean()),
    "ach_share_under_5pct": grp.apply(lambda s: (s < 5).mean()),
}).reset_index()
# normalised by the top achievement so games with big casual audiences compare fairly
top = ach_m["ach_top_pct"].replace(0, np.nan)
ach_m["ach_retention_ratio"] = ach_m["ach_median_pct"] / top
ach_m["ach_tail_ratio"] = ach_m["ach_p10_pct"] / top

# -------------------------------------------------------------- communication
news = pd.read_csv(NEWS)
news["date"] = pd.to_datetime(news["date_unix"], unit="s", utc=True)
news = news.drop_duplicates(["appid", "gid"])
news["word_count"] = news["contents"].fillna("").str.split().str.len()

rows = []
for appid, g in news.groupby("appid"):
    g = g.sort_values("date")
    n_returned = len(g)
    oldest = g["date"].iloc[0]
    truncated = n_returned >= NEWS_COUNT_CAP and oldest > window_start
    # if history is cut off inside the window, shrink the window to what we actually have
    start = oldest if truncated else window_start
    window_days = max((today - start).days, 1)

    w = g[g["date"] >= start]
    stamps = [start] + list(w["date"]) + [today]
    gaps = pd.Series(stamps).diff().dropna().dt.days

    rows.append({
        "appid": appid,
        "n_posts_returned": n_returned,
        "window_truncated": truncated,
        "window_days": window_days,
        "posts_12m": len(w),
        "posts_per_month": len(w) / (window_days / 30.44),
        "active_month_share": w["date"].dt.strftime("%Y-%m").nunique() / math.ceil(window_days / 30.44),
        "longest_gap_days": gaps.max(),
        "days_since_last_post": (today - g["date"].iloc[-1]).days,
        "median_post_words": w["word_count"].median() if len(w) else np.nan,
    })
news_m = pd.DataFrame(rows)

# ---------------------------------------------------------------- assemble
sample = pd.read_csv(SAMPLE)
keep = ["appid", "name", "developer", "publisher", "release_date", "age_days",
        "owners", "positive", "negative", "price", "n_tags_matched", "tags_matched"]
df = sample[[c for c in keep if c in sample.columns]].copy()
df["review_pct_positive"] = df["positive"] / (df["positive"] + df["negative"])
df["owners_low"] = (
    df["owners"].str.split("..", regex=False).str[0]
    .str.replace(",", "", regex=False).str.strip()
    .astype(float)
)

df = df.merge(ach_m, on="appid", how="left").merge(news_m, on="appid", how="left")

# games with no news at all: they communicated zero times, which is information, not missing data
df["has_news"] = df["n_posts_returned"].notna()
df["posts_12m"] = df["posts_12m"].fillna(0)
df["posts_per_month"] = df["posts_per_month"].fillna(0)
df["active_month_share"] = df["active_month_share"].fillna(0)
df["longest_gap_days"] = df["longest_gap_days"].fillna(WINDOW_DAYS)
df["active_month_share"] = df["active_month_share"].clip(upper=1)
df["days_since_last_post"] = df["days_since_last_post"].clip(lower=0)

df.to_csv(OUT_DIR / "game_metrics.csv", index=False)

# ------------------------------------------------------------------ sanity
key = ["ach_median_pct", "ach_share_under_1pct", "ach_retention_ratio", "ach_tail_ratio",
       "posts_per_month", "active_month_share", "longest_gap_days", "days_since_last_post",
       "median_post_words", "review_pct_positive"]
print(f"Rows: {len(df)} | no news: {(~df['has_news']).sum()} | truncated windows: {df['window_truncated'].sum()}")
print("\n--- Distributions ---")
print(df[key].describe().round(2).T.to_string())
print("\n--- Spearman correlations (progression vs communication) ---")
print(df[key].corr(method="spearman").round(2).to_string())
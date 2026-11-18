"""
Step 4: clean the collected data and compute one row of metrics per game.

Input:   data/interim/sample.csv, achievements.csv, news.csv
Output:  data/processed/game_metrics.csv       one row per game (main analysis table)
         data/processed/achievements_clean.csv
         data/processed/news_clean.csv         with cleaned text, post type, in-window flag

Run:  python 04_clean_and_metrics.py
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

INTERIM = Path("data/interim")
OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)

WINDOW_DAYS = 360          # 12 buckets of 30 days: communication metrics use the last year only
NEWS_CAP = 200             # must match NEWS_COUNT in step 3
AS_OF = pd.Timestamp.now(tz="UTC").normalize()
WINDOW_START = AS_OF - pd.Timedelta(days=WINDOW_DAYS)

# Simple rule-based post types (baseline; to be compared with topic modelling later)
POST_TYPE_KEYWORDS = {
    "sale": ["sale", "discount", "% off", "bundle", "deal"],
    "patch": ["patch", "hotfix", "fix", "update", "changelog", "version", "build", "v0.", "v1.", "v2."],
    "event": ["event", "festival", "season", "giveaway", "contest", "stream", "jam", "anniversary"],
    "launch": ["launch", "release", "out now", "available now", "demo", "dlc", "expansion"],
}
TYPES = ["sale", "patch", "event", "launch", "other"]


def classify(title: str) -> str:
    t = str(title).lower()
    for label, words in POST_TYPE_KEYWORDS.items():   # first match wins, in dict order
        if any(w in t for w in words):
            return label
    return "other"


def clean_text(s) -> str:
    s = str(s) if pd.notna(s) else ""
    s = re.sub(r"\[/?[a-zA-Z0-9*]+(?:=[^\]]*)?\]", " ", s)   # BBCode tags
    s = re.sub(r"<[^>]+>", " ", s)                            # HTML tags
    s = re.sub(r"\{STEAM_CLAN_IMAGE\}\S+", " ", s)            # Steam image placeholders
    s = re.sub(r"https?://\S+", " ", s)                       # links
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ load + clean
sample = pd.read_csv(INTERIM / "sample.csv")
ach = pd.read_csv(INTERIM / "achievements.csv")
news = pd.read_csv(INTERIM / "news.csv")

n0 = len(ach)
ach = ach.drop_duplicates(["appid", "achievement"])
bad = ~ach["percent"].between(0, 100)
print(f"Achievements: {n0} rows, {n0 - len(ach)} duplicates removed, {bad.sum()} out-of-range percents dropped")
ach = ach[~bad]

n0 = len(news)
news["date"] = pd.to_datetime(news["date_unix"], unit="s", utc=True)
news = news.dropna(subset=["date"]).drop_duplicates("gid")
print(f"News: {n0} rows, {n0 - len(news)} duplicates/undated removed")
news["text_clean"] = news["contents"].apply(clean_text)
news["text_len"] = news["text_clean"].str.len()
news["post_type"] = news["title"].apply(classify)
news["in_window"] = news["date"] >= WINDOW_START

# ------------------------------------------------------------------ achievement metrics
ach_rows = []
for appid, g in ach.groupby("appid"):
    p = g["percent"]
    ach_rows.append({
        "appid": appid,
        "n_ach": len(p),
        "ach_max_pct": p.max(),
        "ach_median_pct": p.median(),
        "ach_mean_pct": p.mean(),
        "ach_share_below_1pct": (p < 1).mean(),
        "ach_share_above_10pct": (p > 10).mean(),
        "ach_depth_ratio": p.median() / p.max() if p.max() > 0 else np.nan,
    })
ach_m = pd.DataFrame(ach_rows)

# ------------------------------------------------------------------ news metrics (last 12 months)
news_rows = []
for appid, g in news.groupby("appid"):
    g = g.sort_values("date")
    w = g[g["in_window"]]
    d = w["date"]
    gaps = d.diff().dt.total_seconds().dropna() / 86400
    bucket = ((AS_OF - d).dt.days // 30).clip(upper=11)
    row = {
        "appid": appid,
        "posts_retrieved": len(g),
        "oldest_post": g["date"].min(),
        "days_since_last_post": (AS_OF - g["date"].max()).days,
        "posts_12m": len(w),
        "active_month_share": bucket.nunique() / 12 if len(w) else 0.0,
        "median_gap_days": gaps.median() if len(gaps) else np.nan,
        "max_gap_days": gaps.max() if len(gaps) else np.nan,
        "median_post_chars": w["text_len"].median() if len(w) else np.nan,
        # retrieved history does not reach back a full year -> 12-month metrics understate activity
        "window_truncated": bool(len(g) >= NEWS_CAP and g["date"].min() > WINDOW_START),
    }
    for t in TYPES:
        row[f"share_{t}"] = (w["post_type"] == t).mean() if len(w) else np.nan
    news_rows.append(row)
news_m = pd.DataFrame(news_rows)

# ------------------------------------------------------------------ combine
keep = [c for c in ["appid", "name", "developer", "publisher", "owners", "positive", "negative",
                    "price", "release_date", "n_tags_matched", "tags_matched"] if c in sample.columns]
metrics = sample[keep].merge(ach_m, on="appid", how="left").merge(news_m, on="appid", how="left")
metrics["posts_12m"] = metrics["posts_12m"].fillna(0)             # no news at all = silent studio
metrics["active_month_share"] = metrics["active_month_share"].fillna(0.0)
metrics["pos_review_pct"] = metrics["positive"] / (metrics["positive"] + metrics["negative"]) * 100

metrics.to_csv(OUT / "game_metrics.csv", index=False)
ach.to_csv(OUT / "achievements_clean.csv", index=False)
news.to_csv(OUT / "news_clean.csv", index=False)

# ------------------------------------------------------------------ summary
print(f"\nGames in metrics table: {len(metrics)}")
print(f"Games with no news posts at all: {(metrics['posts_retrieved'].isna()).sum()}")
print(f"Games with window_truncated=True: {int(metrics['window_truncated'].fillna(False).sum())}")
cols = ["n_ach", "ach_max_pct", "ach_median_pct", "ach_share_below_1pct", "ach_depth_ratio",
        "posts_12m", "active_month_share", "median_gap_days", "max_gap_days", "median_post_chars",
        "pos_review_pct"]
print("\n" + metrics[cols].describe().round(2).T.to_string())
print("\nPost type mix (last 12 months, all games pooled):")
print(news[news["in_window"]]["post_type"].value_counts(normalize=True).round(3).to_string())
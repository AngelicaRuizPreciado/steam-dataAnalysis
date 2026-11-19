"""
Step 5: load the collected data into SQLite and rebuild the metrics with SQL.

Input:   data/interim/sample.csv, achievements.csv, news.csv   and   sql/metrics.sql
Output:  data/steam.db                          (tables: games, achievements, news; views: game_metrics, ...)
         data/processed/game_metrics_sql.csv    (export of the game_metrics view)

Run:  python 05_build_database.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

DB = Path("data/steam.db")
SQL_FILE = Path("sql/Metrics.sql")
OUT = Path("data/processed/game_metrics_sql.csv")
REF = Path("data/processed/game_metrics.csv")   # pandas version from step 4, used as a cross-check
OUT.parent.mkdir(parents=True, exist_ok=True)

games = pd.read_csv("data/interim/sample.csv")
games = games[[c for c in ["appid", "name", "developer", "publisher", "release_date", "age_days",
                           "owners", "positive", "negative", "price", "n_tags_matched", "tags_matched"]
               if c in games.columns]]

ach = pd.read_csv("data/interim/achievements.csv")

news = pd.read_csv("data/interim/news.csv")
news["word_count"] = news["contents"].fillna("").str.split().str.len()
news = news.dropna(subset=["date_unix"])
news["date_unix"] = news["date_unix"].astype("int64")
news = news[["appid", "gid", "title", "url", "author", "feedlabel", "feedname", "date_unix", "contents", "word_count"]]

with sqlite3.connect(DB) as con:
    games.to_sql("games", con, if_exists="replace", index=False)
    ach.to_sql("achievements", con, if_exists="replace", index=False)
    news.to_sql("news", con, if_exists="replace", index=False)
    con.executescript(SQL_FILE.read_text(encoding="utf-8"))

    out = pd.read_sql("SELECT * FROM game_metrics", con)
    capped = con.execute(
        "SELECT COUNT(*) FROM news_overall o CROSS JOIN params p "
        "WHERE o.n_posts_returned >= 200 AND o.oldest_ts > p.window_start"
    ).fetchone()[0]

out.to_csv(OUT, index=False)
print(f"Tables loaded: games={len(games)}, achievements={len(ach)}, news={len(news)}")
print(f"game_metrics rows: {len(out)} | no news: {(out['has_news'] == 0).sum()} | "
      f"low-signal achievements: {out['low_signal_achievements'].sum()}")
print(f"Games whose 200-post cap cuts into the 12-month window: {capped} (must be 0)")

# cross-check against the pandas version from step 4
if REF.exists():
    ref = pd.read_csv(REF).set_index("appid")
    new = out.set_index("appid")
    cols = ["ach_median_pct", "ach_p10_pct", "ach_share_under_1pct", "ach_retention_ratio", "ach_tail_ratio",
            "posts_12m", "posts_per_month", "active_month_share", "longest_gap_days",
            "days_since_last_post", "median_post_words"]
    cols = [c for c in cols if c in ref.columns]
    diff = (ref[cols] - new.loc[ref.index, cols]).abs().max()
    print("\nMax absolute difference, SQL vs pandas (expect ~0):")
    print(diff.round(6).to_string())
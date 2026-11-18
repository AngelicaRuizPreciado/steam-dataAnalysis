"""
Step 3: collect achievement unlock rates and news posts for every game in the sample.

Input:   data/interim/sample.csv
Cache:   data/raw/achievements/<appid>.json
         data/raw/news/<appid>.json
Output:  data/interim/achievements.csv   one row per (game, achievement)
         data/interim/news.csv           one row per (game, news post)
         data/interim/collection_log.csv per game: what was retrieved / what failed

Run:  python 03_collect_game_data.py
Neither endpoint needs an API key. Reruns skip anything already cached.
"""
import json
import time
from pathlib import Path

import pandas as pd
import requests

SAMPLE = Path("data/interim/sample.csv")
ACH_DIR = Path("data/raw/achievements")
NEWS_DIR = Path("data/raw/news")
ACH_DIR.mkdir(parents=True, exist_ok=True)
NEWS_DIR.mkdir(parents=True, exist_ok=True)

ACH_URL = "https://api.steampowered.com/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v0002/"
NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/"

NEWS_COUNT = 200          # max posts per game; games hitting this are flagged
NEWS_MAXLENGTH = 0        # 0 = full text (needed later for text analysis)
NEWS_FEEDS = "steam_community_announcements"  # the studio's own posts (excludes press articles)
DELAY = 0.5


def get_json(url: str, params: dict, retries: int = 4):
    """GET with retries; returns (json_or_None, status_note)."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code in (403, 404):
                return None, f"http {r.status_code}"
            if r.status_code == 429:
                time.sleep(30 * attempt)
                continue
            r.raise_for_status()
            return r.json(), "ok"
        except (requests.RequestException, ValueError) as e:
            time.sleep(5 * attempt)
            note = f"error: {e}"
    return None, note


def cached(path: Path, url: str, params: dict):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), "cached"
    data, note = get_json(url, params)
    if data is not None:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(DELAY)
    return data, note


def main() -> None:
    sample = pd.read_csv(SAMPLE)
    ach_rows, news_rows, log_rows = [], [], []

    for i, row in enumerate(sample.itertuples(), start=1):
        appid, name = int(row.appid), row.name
        print(f"[{i}/{len(sample)}] {appid} {name}")

        # --- achievements ---
        ach, ach_note = cached(ACH_DIR / f"{appid}.json", ACH_URL, {"gameid": appid, "format": "json"})
        n_ach = 0
        if ach:
            items = ach.get("achievementpercentages", {}).get("achievements", [])
            n_ach = len(items)
            for a in items:
                ach_rows.append({"appid": appid, "achievement": a.get("name"), "percent": float(a.get("percent"))})

        # --- news ---
        news, news_note = cached(
            NEWS_DIR / f"{appid}.json",
            NEWS_URL,
            {"appid": appid, "count": NEWS_COUNT, "maxlength": NEWS_MAXLENGTH,
             "feeds": NEWS_FEEDS, "format": "json"},
        )
        n_news = 0
        if news:
            items = news.get("appnews", {}).get("newsitems", [])
            n_news = len(items)
            for n in items:
                news_rows.append({
                    "appid": appid,
                    "gid": n.get("gid"),
                    "title": n.get("title"),
                    "url": n.get("url"),
                    "author": n.get("author"),
                    "feedlabel": n.get("feedlabel"),
                    "feedname": n.get("feedname"),
                    "date_unix": n.get("date"),
                    "contents": n.get("contents"),
                })

        log_rows.append({
            "appid": appid, "name": name,
            "ach_status": ach_note, "n_achievements_returned": n_ach,
            "news_status": news_note, "n_news_returned": n_news,
            "news_possibly_truncated": n_news >= NEWS_COUNT,
        })

    ach_df = pd.DataFrame(ach_rows)
    news_df = pd.DataFrame(news_rows)
    if not news_df.empty:
        news_df["date"] = pd.to_datetime(news_df["date_unix"], unit="s", utc=True)
    log_df = pd.DataFrame(log_rows)

    ach_df.to_csv("data/interim/achievements.csv", index=False)
    news_df.to_csv("data/interim/news.csv", index=False)
    log_df.to_csv("data/interim/collection_log.csv", index=False)

    print("\n--- Collection summary ---")
    print(f"Games with achievement data: {(log_df['n_achievements_returned'] > 0).sum()} / {len(log_df)}")
    print(f"Games with >=1 news post:    {(log_df['n_news_returned'] > 0).sum()} / {len(log_df)}")
    print(f"Games with possibly truncated news (>= {NEWS_COUNT} posts): {log_df['news_possibly_truncated'].sum()}")
    print(f"Total achievement rows: {len(ach_df)} | total news rows: {len(news_df)}")
    print("\nNews posts per game:")
    print(log_df["n_news_returned"].describe().round(1).to_string())


if __name__ == "__main__":
    main()
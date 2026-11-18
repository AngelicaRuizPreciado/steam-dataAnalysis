"""
Step 1: collect candidate games from SteamSpy by community tag.

Output:
  data/raw/steamspy_<tag>.json   raw API response (kept untouched)
  data/interim/candidates_<tag>.csv   flat table, one row per game

Run:  python 01_collect_candidates.py
"""
import json
import time
from pathlib import Path

import pandas as pd
import requests

TAGS = ["Cozy", "Wholesome", "Relaxing", "Farming Sim", "Life Sim"]
STEAMSPY_URL = "https://steamspy.com/api.php"

RAW_DIR = Path("data/raw")
INTERIM_DIR = Path("data/interim")
RAW_DIR.mkdir(parents=True, exist_ok=True)
INTERIM_DIR.mkdir(parents=True, exist_ok=True)


def fetch_tag(tag: str, retries: int = 3) -> dict:
    """Return {appid: game_dict} for all games SteamSpy lists under a tag."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(
                STEAMSPY_URL,
                params={"request": "tag", "tag": tag},
                timeout=60,
            )
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"[{tag}] attempt {attempt} failed: {e}")
            time.sleep(10 * attempt)
    raise RuntimeError(f"Could not fetch tag '{tag}'")


def main() -> None:
    frames = []
    for tag in TAGS:
        data = fetch_tag(tag)
        print(f"[{tag}] games returned: {len(data)}")

        raw_path = RAW_DIR / f"steamspy_{tag.lower().replace(' ', '_')}.json"
        raw_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        df = pd.DataFrame.from_dict(data, orient="index")
        df["source_tag"] = tag
        df.to_csv(INTERIM_DIR / f"candidates_{tag.lower().replace(' ', '_')}.csv", index=False)
        frames.append(df)

        # quick look so you can sanity-check the sample
        cols = [c for c in ["appid", "name", "developer", "owners", "positive", "negative"] if c in df.columns]
        print(df[cols].head(10).to_string(index=False))
        print(df.columns.tolist())
        time.sleep(2)  # be polite between tag requests

    # merge all tags: one row per game, plus which tags it appeared under
    all_df = pd.concat(frames, ignore_index=True)
    keep_cols = [c for c in all_df.columns if c not in ("appid", "source_tag")]
    merged = (
        all_df.groupby("appid")
        .agg(
            **{c: (c, "first") for c in keep_cols},
            tags_matched=("source_tag", lambda s: ", ".join(sorted(set(s)))),
            n_tags_matched=("source_tag", "nunique"),
        )
        .reset_index()
    )
    merged.to_csv(INTERIM_DIR / "candidates_all.csv", index=False)
    print(f"\nMerged pool: {len(merged)} unique games")
    print(merged["n_tags_matched"].value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
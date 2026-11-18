"""
Step 2: enrich candidates with Steam store data and apply inclusion filters.

Input:   data/interim/candidates_cozy.csv   (from step 1)
Cache:   data/raw/appdetails/<appid>.json   (one file per game; reruns skip these)
Output:  data/interim/sample.csv             (games that pass all filters)
         data/interim/filter_log.csv         (every candidate + why it was kept/dropped)

Run:  python 02_enrich_filter.py
Takes ~4-5 minutes for ~126 games (Steam appdetails is rate limited).
"""
import json
import time
from pathlib import Path

import pandas as pd
import requests

# ---- inclusion criteria (edit here, rerun; cached data is reused) ----
REQUIRED_GENRE = "Indie"
MIN_AGE_DAYS = 365          # released at least 12 months ago
MIN_ACHIEVEMENTS = 10
# ----------------------------------------------------------------------

CANDIDATES = Path("data/interim/candidates_all.csv")
CACHE_DIR = Path("data/raw/appdetails")
OUT_SAMPLE = Path("data/interim/sample.csv")
OUT_LOG = Path("data/interim/filter_log.csv")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

URL = "https://store.steampowered.com/api/appdetails"
DELAY = 1.6  # seconds between calls, keeps us under ~200 requests / 5 min


def fetch_appdetails(appid: int, retries: int = 4) -> dict:
    """Return the store record for one app, using the local cache if present."""
    cache_file = CACHE_DIR / f"{appid}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    for attempt in range(1, retries + 1):
        try:
            r = requests.get(URL, params={"appids": appid, "cc": "us", "l": "english"}, timeout=30)
            if r.status_code == 429:
                wait = 60 * attempt
                print(f"  rate limited, waiting {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            payload = r.json().get(str(appid), {"success": False})
            cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            time.sleep(DELAY)
            return payload
        except (requests.RequestException, ValueError) as e:
            print(f"  appid {appid} attempt {attempt} failed: {e}")
            time.sleep(10 * attempt)
    return {"success": False, "error": "failed after retries"}


def parse_record(appid: int, payload: dict) -> dict:
    """Flatten the fields we need; missing data becomes None."""
    row = {"appid": appid, "api_success": bool(payload.get("success"))}
    d = payload.get("data") or {}
    row["type"] = d.get("type")
    row["release_date_raw"] = (d.get("release_date") or {}).get("date")
    row["coming_soon"] = (d.get("release_date") or {}).get("coming_soon")
    row["genres"] = ", ".join(g["description"] for g in d.get("genres", []))
    row["n_achievements"] = (d.get("achievements") or {}).get("total", 0)
    return row


def main() -> None:
    cand = pd.read_csv(CANDIDATES)
    print(f"Candidates: {len(cand)}")

    rows = []
    for i, appid in enumerate(cand["appid"], start=1):
        print(f"[{i}/{len(cand)}] {appid}")
        rows.append(parse_record(int(appid), fetch_appdetails(int(appid))))

    details = pd.DataFrame(rows)
    df = cand.merge(details, on="appid", how="left")
    df["release_date"] = pd.to_datetime(df["release_date_raw"], errors="coerce", format="mixed")
    df["age_days"] = (pd.Timestamp.today().normalize() - df["release_date"]).dt.days

    # apply filters one by one and record the first reason each game fails
    def reason(r) -> str:
        if not r["api_success"]:
            return "no store data"
        if r["type"] != "game":
            return "not a game"
        if REQUIRED_GENRE not in str(r["genres"]):
            return f"not tagged {REQUIRED_GENRE} (store genre)"
        if pd.isna(r["age_days"]):
            return "release date missing or unparsed"
        if r["age_days"] < MIN_AGE_DAYS:
            return "released < 12 months ago"
        if r["n_achievements"] < MIN_ACHIEVEMENTS:
            return f"fewer than {MIN_ACHIEVEMENTS} achievements"
        return "kept"

    df["filter_result"] = df.apply(reason, axis=1)
    df.to_csv(OUT_LOG, index=False)
    df[df["filter_result"] == "kept"].to_csv(OUT_SAMPLE, index=False)

    print("\n--- Filter summary ---")
    print(df["filter_result"].value_counts().to_string())
    print(f"\nFinal sample: {(df['filter_result'] == 'kept').sum()} games -> {OUT_SAMPLE}")


if __name__ == "__main__":
    main()
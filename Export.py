"""
Step 8: export dashboard-ready CSVs for Power BI, with human-readable column names and values.

Input:   data/steam.db (steps 5-7), data/processed/segment_summary.csv, post_type_correlations.csv
Output:  data/powerbi/scorecard.csv                 one row per game, rated against segment peers
         data/powerbi/segment_summary.csv           medians per activity segment
         data/powerbi/post_type_correlations.csv    controlled correlations by post type

Run:  python 08_export_for_powerbi.py
CSV format: semicolon-separated, decimal comma (e.g. 0,841), UTF-8 with BOM.
Share-type columns are exported on a 0-100 scale, so "(%)" columns read directly.
"""
import sqlite3
from pathlib import Path

import pandas as pd

OUT = Path("data/powerbi")
# Italian-locale CSV: semicolon separator, decimal comma, UTF-8 with BOM (Power BI on an Italian system reads it natively)
CSV = dict(index=False, sep=";", decimal=",", encoding="utf-8-sig")
OUT.mkdir(parents=True, exist_ok=True)

SEGMENTS = {"dormant": "Dormant", "occasional": "Occasional", "active": "Active"}
OUTCOMES = {
    "ach_retention_ratio": "Retention Ratio",
    "ach_tail_ratio": "Late-Game Reach",
    "ach_share_under_1pct": "Rare Achievements",
}
POST_TYPES = {"n_update": "Update", "n_sale": "Sale", "n_event": "Event", "n_other": "Other"}

# ------------------------------------------------------------------ scorecard
with sqlite3.connect("data/steam.db") as con:
    con.executescript(Path("sql/segments.sql").read_text(encoding="utf-8"))
    con.executescript(Path("sql/scorecard.sql").read_text(encoding="utf-8"))
    sc = pd.read_sql("SELECT * FROM scorecard ORDER BY segment_order, ach_retention_ratio DESC", con)

sc["segment_label"] = sc["segment_label"].map(SEGMENTS)
sc["low_signal_achievements"] = sc["low_signal_achievements"].map({0: "No", 1: "Yes"})
for c in ["review_pct_positive", "ach_share_under_1pct", "retention_pctile"]:
    sc[c] = sc[c] * 100

sc = sc.rename(columns={
    "appid": "Steam App ID", "name": "Game", "segment_label": "Activity Segment",
    "segment_order": "Segment Order", "age_days": "Game Age (Days)",
    "owners_low": "Owners (Lower Bound)", "review_pct_positive": "Positive Reviews (%)",
    "posts_12m": "Posts (Last 12 Months)", "days_since_last_post": "Days Since Last Post",
    "median_post_words": "Typical Post Length (Words)",
    "ach_retention_ratio": "Achievement Retention Ratio",
    "ach_tail_ratio": "Late-Game Reach Ratio",
    "ach_share_under_1pct": "Rare Achievements (%)",
    "low_signal_achievements": "Excluded: Low Signal",
    "retention_pctile": "Peer Percentile (0-100)", "peer_rating": "Peer Rating",
})
sc.round(3).to_csv(OUT / "scorecard.csv", **CSV)

# ------------------------------------------------------------ segment summary
seg = pd.read_csv("data/processed/segment_summary.csv")
seg["segment_label"] = seg["activity_segment"].str[2:].map(SEGMENTS)
seg["Segment Order"] = seg["activity_segment"].str[0].astype(int)
for c in ["review_pct_positive", "ach_share_under_1pct"]:
    seg[c] = seg[c] * 100
seg = seg.drop(columns="activity_segment").rename(columns={
    "segment_label": "Activity Segment", "n": "Games",
    "ach_retention_ratio": "Median Retention Ratio", "ach_tail_ratio": "Median Late-Game Reach Ratio",
    "ach_share_under_1pct": "Median Rare Achievements (%)",
    "review_pct_positive": "Median Positive Reviews (%)",
    "age_days": "Median Game Age (Days)", "owners_low": "Median Owners (Lower Bound)",
    "posts_12m": "Median Posts (Last 12 Months)",
})
cols = ["Activity Segment", "Segment Order", "Games"] + [c for c in seg.columns if c not in ("Activity Segment", "Segment Order", "Games")]
seg[cols].round(3).to_csv(OUT / "segment_summary.csv", **CSV)

# --------------------------------------------------- post type correlations
pc = pd.read_csv("data/processed/post_type_correlations.csv")
pc["post_type"] = pc["post_type"].map(POST_TYPES)
pc["outcome"] = pc["outcome"].map(OUTCOMES)
pc["Significant (Controlled, p < 0.05)"] = (pc["p_controlled"] < 0.05).map({True: "Yes", False: "No"})
pc = pc.rename(columns={
    "post_type": "Post Type", "outcome": "Outcome", "n": "Games",
    "rho_raw": "Correlation (Raw)", "p_raw": "p-value (Raw)",
    "rho_controlled": "Correlation (Controlled)", "p_controlled": "p-value (Controlled)",
})
pc.to_csv(OUT / "post_type_correlations.csv", **CSV)

print(f"scorecard rows: {len(sc)}")
print(sc["Peer Rating"].value_counts().to_string())
print("\nSegment summary columns:", list(seg[cols].columns))
print("Post types:", pc["Post Type"].unique().tolist(), "| Outcomes:", pc["Outcome"].unique().tolist())
print(f"\nFiles written to {OUT}/")
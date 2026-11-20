"""
Step 9: figure for the Business Problem section of the README.

Shows two games side by side: achievements ordered from most to least unlocked,
with the median (retention ratio) and the hardest tenth (late-game reach) marked.

Input:   data/steam.db (steps 5-6)
Output:  images/business_problem.png

Usage:
  python 09_figure_business_problem.py                       lists candidate games
  python 09_figure_business_problem.py "Dormant game" "Active game"   draws the figure
"""
import sqlite3
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DB = Path("data/steam.db")
OUT = Path("images/business_problem.png")
OUT.parent.mkdir(parents=True, exist_ok=True)

GREY, BLUE, RED = "#BFC5CC", "#1F4E79", "#C0504D"

BASE_QUERY = """
SELECT b.appid, b.name, b.activity_segment AS segment, g.n_achievements_api AS n_ach,
       ROUND(b.ach_retention_ratio, 2) AS retention, ROUND(b.ach_tail_ratio, 2) AS reach,
       ROUND(g.review_pct_positive * 100) AS reviews_pct, b.posts_12m
FROM analysis_base b JOIN game_metrics g ON g.appid = b.appid
WHERE b.low_signal_achievements = 0 AND g.n_achievements_api >= 12
"""

with sqlite3.connect(DB) as con:
    games = pd.read_sql(BASE_QUERY, con)
    games = games[games["name"].map(lambda s: str(s).isascii())]   # avoid font problems with non-Latin names

    if len(sys.argv) != 3:
        print("Dormant studios with the highest retention (pick one):")
        print(games[games.segment == "1_dormant"].nlargest(8, "retention")
              .drop(columns=["appid", "segment"]).to_string(index=False))
        print("\nActive studios with the lowest retention (pick one):")
        print(games[games.segment == "3_active"].nsmallest(8, "retention")
              .drop(columns=["appid", "segment"]).to_string(index=False))
        print('\nThen run:  python 09_figure_business_problem.py "Dormant game" "Active game"')
        sys.exit(0)

    chosen = []
    for name in sys.argv[1:3]:
        row = games[games["name"] == name]
        if row.empty:
            sys.exit(f'Game "{name}" not found among the candidates (check spelling).')
        row = row.iloc[0]
        pct = pd.read_sql("SELECT percent FROM achievements WHERE appid = ?", con, params=(int(row["appid"]),))["percent"]
        chosen.append((row, np.sort(pct.to_numpy())[::-1]))

fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
ymax = max(p.max() for _, p in chosen) * 1.18

for ax, (row, pct) in zip(axes, chosen):
    median, p10 = np.median(pct), np.percentile(pct, 10)
    ax.bar(range(len(pct)), pct, color=GREY, width=0.85)
    ax.axhline(median, color=BLUE, ls="--", lw=1.4)
    ax.axhline(p10, color=RED, ls="--", lw=1.4)
    ax.text(0.97, 0.93, f"- - Typical achievement: {median:.0f}% of players\n      retention ratio {row['retention']:.2f}",
            transform=ax.transAxes, color=BLUE, ha="right", va="top", fontsize=9)
    ax.text(0.97, 0.72, f"- - Hardest tenth: {p10:.1f}% or fewer\n      late-game reach {row['reach']:.2f}",
            transform=ax.transAxes, color=RED, ha="right", va="top", fontsize=9)
    ax.text(0, pct[0] + ymax * 0.015, f"Easiest: {pct[0]:.0f}%", fontsize=8.5, va="bottom")
    kind = "Dormant studio, no posts in 12 months" if row["segment"] == "1_dormant" \
        else f"Active studio, {int(row['posts_12m'])} posts in 12 months"
    ax.set_title(f"{row['name']}\n{kind}", fontsize=10)
    ax.set_xlabel("Achievements, from most to least unlocked", fontsize=9)
    ax.set_xticks([])
    ax.set_ylim(0, ymax)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

axes[0].set_ylabel("Players who unlocked it (%)", fontsize=9)
fig.suptitle("Same measure, two games: where do players stop?", fontsize=12, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.96))
fig.savefig(OUT, dpi=170)
print(f"Saved {OUT}")
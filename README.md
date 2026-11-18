# Steam Game Health Scorecard (WIP)
_Benchmarking player progression and studio communication across indie and cozy game titles._

## Summary
This project builds a scorecard that compares around 50 indie and cozy games on Steam along two dimensions: how far players progress (from global achievement unlock rates) and how actively and in what way studios communicate (from news feed history). It identifies which titles show healthy content engagement and which show warning signs. Key finding: (TODO).

## Business Problem

A publisher deciding where to spend post-launch support and marketing budget needs to know which games in its portfolio are worth it. Two questions:

* Progression: do players reach the late content, or do they drop off early?

* Communication: do studios keep players informed regularly, and does their cadence and content type differ between strong and weak titles?

**Stakeholder:** A hypothetical publisher or live-ops team. 

**Decision supported:** Which games to prioritize, fix, or deprioritize.

## Methodology
Data collection: pull GetGlobalAchievementPercentagesForApp and GetNewsForApp for around 50 games via Python, and store the raw responses in PostgreSQL.

Cleaning: drop games without achievements, deduplicate news posts, convert UNIX timestamps.

Progression metrics: median unlock rate, share of achievements under 1%, and the steepness of the unlock-rate curve per game.

Communication metrics: posts per month, gaps between posts, post length, and feed label. Topic modeling classifies posts as patch notes, events, sales or announcements.

Scoring: combine the metrics into a per-game score and compare within the genre.

Visualization: Power BI dashboard.

***Limitations**: achievement rates are a snapshot and not a true progression order, and news data has no engagement outcome, so findings are exploratory rather than causal. The API used to retrieve games by tag (SteamSpy) is not official and may be incomplete, it also returns games by how famous they are, so results may be biased.*
## Skills

Python (requests, pandas), SQL, API data collection, data cleaning, NLP and topic modeling, statistical benchmarking, dashboarding, business storytelling.

## Results & Business Recommendation (TODO)
Headline findings: [3 bullets]
Game classification: [e.g. healthy / at risk / underperforming]
Recommendations: [what the publisher should do, tied to evidence]
Limitations and next steps: [what extra data would strengthen this]
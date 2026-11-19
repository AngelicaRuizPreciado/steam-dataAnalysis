-- metrics.sql: rebuilds the game-level metrics as SQL views (SQLite >= 3.25, window functions).
-- Tables expected: games, achievements, news (loaded by 05_build_database.py).

CREATE INDEX IF NOT EXISTS idx_ach_appid  ON achievements(appid);
CREATE INDEX IF NOT EXISTS idx_news_appid ON news(appid);

DROP VIEW IF EXISTS game_metrics;
DROP VIEW IF EXISTS news_metrics;
DROP VIEW IF EXISTS news_overall;
DROP VIEW IF EXISTS news_window;
DROP VIEW IF EXISTS news_clean;
DROP VIEW IF EXISTS ach_metrics;
DROP VIEW IF EXISTS params;

-- Reference dates: today (start of day, UTC) and the start of the 12-month window.
CREATE VIEW params AS
SELECT CAST(strftime('%s', 'now', 'start of day') AS INTEGER)                  AS today_ts,
       CAST(strftime('%s', 'now', 'start of day') AS INTEGER) - 365 * 86400    AS window_start;

-- ---------------------------------------------------------------- progression
CREATE VIEW ach_metrics AS
WITH ranked AS (
    SELECT appid, percent,
           ROW_NUMBER() OVER (PARTITION BY appid ORDER BY percent) AS rn,
           COUNT(*)     OVER (PARTITION BY appid)                  AS n
    FROM achievements
),
agg AS (
    SELECT appid,
           MAX(n)       AS n_achievements_api,
           MAX(percent) AS ach_top_pct,
           -- median: average of the middle one or two values
           AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2) THEN percent END) AS ach_median_pct,
           -- 10th percentile with linear interpolation (same method as pandas)
           MAX(CASE WHEN rn - 1 = CAST(0.1 * (n - 1) AS INTEGER)     THEN percent END) AS p10_lo,
           MAX(CASE WHEN rn - 1 = CAST(0.1 * (n - 1) AS INTEGER) + 1 THEN percent END) AS p10_hi,
           MAX(0.1 * (n - 1) - CAST(0.1 * (n - 1) AS INTEGER))                         AS p10_frac,
           AVG(percent < 1) AS ach_share_under_1pct,
           AVG(percent < 5) AS ach_share_under_5pct
    FROM ranked
    GROUP BY appid
),
p AS (
    SELECT *, p10_lo + (COALESCE(p10_hi, p10_lo) - p10_lo) * p10_frac AS ach_p10_pct
    FROM agg
)
SELECT appid, n_achievements_api, ach_top_pct, ach_median_pct, ach_p10_pct,
       ach_share_under_1pct, ach_share_under_5pct,
       ach_median_pct / NULLIF(ach_top_pct, 0) AS ach_retention_ratio,
       ach_p10_pct    / NULLIF(ach_top_pct, 0) AS ach_tail_ratio
FROM p;

-- -------------------------------------------------------------- communication
-- one row per (game, post); duplicates removed
CREATE VIEW news_clean AS
SELECT appid, gid, MAX(date_unix) AS date_unix, MAX(word_count) AS word_count
FROM news
GROUP BY appid, gid;

-- all-time facts per game (also used to check that the 200-post cap does not bite)
CREATE VIEW news_overall AS
SELECT appid,
       COUNT(*)       AS n_posts_returned,
       MIN(date_unix) AS oldest_ts,
       MAX(date_unix) AS last_post_ts
FROM news_clean
GROUP BY appid;

-- posts inside the 12-month window, with the previous post's timestamp and a word-count rank
CREATE VIEW news_window AS
SELECT c.appid, c.date_unix, c.word_count,
       LAG(c.date_unix) OVER (PARTITION BY c.appid ORDER BY c.date_unix) AS prev_ts,
       ROW_NUMBER()     OVER (PARTITION BY c.appid ORDER BY c.word_count) AS wc_rn,
       COUNT(*)         OVER (PARTITION BY c.appid)                       AS wc_n
FROM news_clean c CROSS JOIN params p
WHERE c.date_unix >= p.window_start;

CREATE VIEW news_metrics AS
SELECT appid,
       COUNT(*)                                                        AS posts_12m,
       COUNT(DISTINCT strftime('%Y-%m', date_unix, 'unixepoch'))       AS active_months_12m,
       MAX((date_unix - prev_ts) / 86400)                              AS max_inner_gap_days,
       MIN(date_unix)                                                  AS first_ts_12m,
       MAX(date_unix)                                                  AS last_ts_12m,
       AVG(CASE WHEN wc_rn IN ((wc_n + 1) / 2, (wc_n + 2) / 2) THEN word_count END) AS median_post_words
FROM news_window
GROUP BY appid;

-- ------------------------------------------------------------------- final table
CREATE VIEW game_metrics AS
SELECT g.appid, g.name, g.developer, g.publisher, g.release_date, g.age_days,
       g.owners,
       CAST(REPLACE(SUBSTR(g.owners, 1, INSTR(g.owners, ' ') - 1), ',', '') AS REAL) AS owners_low,
       g.positive, g.negative, g.price, g.n_tags_matched, g.tags_matched,
       1.0 * g.positive / (g.positive + g.negative) AS review_pct_positive,

       a.n_achievements_api, a.ach_top_pct, a.ach_median_pct, a.ach_p10_pct,
       a.ach_share_under_1pct, a.ach_share_under_5pct,
       a.ach_retention_ratio, a.ach_tail_ratio,
       CASE WHEN a.ach_top_pct < 5 THEN 1 ELSE 0 END AS low_signal_achievements,

       CASE WHEN o.appid IS NOT NULL THEN 1 ELSE 0 END AS has_news,
       COALESCE(nm.posts_12m, 0)                        AS posts_12m,
       1.0 * COALESCE(nm.posts_12m, 0) / (365 / 30.44)  AS posts_per_month,
       MIN(1.0, COALESCE(nm.active_months_12m, 0) / 12.0) AS active_month_share,
       CASE WHEN nm.posts_12m IS NULL THEN 365
            ELSE MAX(COALESCE(nm.max_inner_gap_days, 0),
                     (nm.first_ts_12m - p.window_start) / 86400,
                     (p.today_ts - nm.last_ts_12m) / 86400) END AS longest_gap_days,
       CASE WHEN o.appid IS NULL THEN NULL
            ELSE MAX(0, (p.today_ts - o.last_post_ts) / 86400) END AS days_since_last_post,
       nm.median_post_words
FROM games g
CROSS JOIN params p
LEFT JOIN ach_metrics  a  ON a.appid  = g.appid
LEFT JOIN news_overall o  ON o.appid  = g.appid
LEFT JOIN news_metrics nm ON nm.appid = g.appid;
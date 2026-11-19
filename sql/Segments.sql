-- segments.sql: analysis base table. One row per game, with activity segment and age/size bands.
-- Progression metrics are NULLed for low-signal games (top achievement < 5% of players).
DROP VIEW IF EXISTS analysis_base;
CREATE VIEW analysis_base AS
WITH seg AS (
    SELECT *,
           CASE WHEN posts_12m = 0  THEN '1_dormant'      -- no posts in 12 months
                WHEN posts_12m < 12 THEN '2_occasional'   -- under 1 post per month
                ELSE                     '3_active'       -- 1+ posts per month
           END AS activity_segment,
           NTILE(3) OVER (ORDER BY age_days)   AS age_band,    -- 1 = youngest third
           NTILE(3) OVER (ORDER BY owners_low) AS size_band    -- 1 = smallest third
    FROM game_metrics
)
SELECT appid, name, activity_segment, age_band, size_band, age_days, owners_low,
       review_pct_positive, posts_12m, posts_per_month, days_since_last_post, median_post_words,
       low_signal_achievements,
       CASE WHEN low_signal_achievements = 0 THEN ach_retention_ratio    END AS ach_retention_ratio,
       CASE WHEN low_signal_achievements = 0 THEN ach_tail_ratio         END AS ach_tail_ratio,
       CASE WHEN low_signal_achievements = 0 THEN ach_share_under_1pct   END AS ach_share_under_1pct,
       CASE WHEN low_signal_achievements = 0 THEN ach_median_pct         END AS ach_median_pct
FROM seg;
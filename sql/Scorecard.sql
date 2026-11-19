-- scorecard.sql: per-game scorecard for the dashboard, rated against peers in the same activity segment.
DROP VIEW IF EXISTS scorecard;
CREATE VIEW scorecard AS
WITH r AS (
    SELECT *,
           PERCENT_RANK() OVER (PARTITION BY activity_segment ORDER BY ach_retention_ratio) AS retention_pctile
    FROM analysis_base
    WHERE low_signal_achievements = 0
)
SELECT b.appid, b.name,
       SUBSTR(b.activity_segment, 3)                  AS segment_label,     -- dormant / occasional / active
       CAST(SUBSTR(b.activity_segment, 1, 1) AS INT)  AS segment_order,
       b.age_days, b.owners_low, b.review_pct_positive,
       b.posts_12m, b.days_since_last_post, b.median_post_words,
       b.ach_retention_ratio, b.ach_tail_ratio, b.ach_share_under_1pct,
       b.low_signal_achievements,
       r.retention_pctile,
       CASE WHEN b.low_signal_achievements = 1 THEN 'Excluded (low signal)'
            WHEN r.retention_pctile >= 0.75     THEN 'Above peers'
            WHEN r.retention_pctile <= 0.25     THEN 'Below peers'
            ELSE 'In line with peers' END             AS peer_rating
FROM analysis_base b
LEFT JOIN r ON r.appid = b.appid;
-- ################
-- Initial Question:
-- "What are my top 10 profit potential articles last 30 days?"
-- ################
-- Revised Question:
-- What are the top 10 profit potential articles in US stores from 2026-05-01 to 2026-05-31?
-- ################
-- Answer:
-- Top 10 results, ordered by highest GP0 potential.
-- Query run date: 2026-07-17.
--
-- item_no  | dns_k  | budget_sales_k | gp0_k | actual_gm0_pct | us_benchmark_gm0_pct | gp0_potential_k
-- 80275887 | 143325 | 146064         | 43879 | 30.04           | 45.79                 | 23005
-- 30102974 | 57328  | 58825          | 8331  | 14.16           | 45.79                 | 18605
-- 20275885 | 108622 | 110982         | 35574 | 32.05           | 45.79                 | 15246
-- 20275814 | 62980  | 65561          | 15024 | 22.92           | 45.79                 | 14997
-- 50097995 | 31782  | 26709          | 2409  | 9.02            | 45.79                 | 9822
-- 70086401 | 16949  | 13194          | -3553 | -26.93          | 45.79                 | 9595
-- 30238543 | 21542  | 21914          | 1536  | 7.01            | 45.79                 | 8499
-- 00275848 | 34337  | 35259          | 7660  | 21.72           | 45.79                 | 8486
-- 30349329 | 47321  | 48546          | 13799 | 28.42           | 45.79                 | 8431
-- 60275812 | 34283  | 35503          | 7962  | 22.43           | 45.79                 | 8295
-- ################
-- Assumptions/Doubts:
-- - Retail Unit US is used.
-- - The window starts on 2026-05-01 and ends on 2026-05-31.
-- - Profit potential is measured as the GP0 gap to the US benchmark GM0.
-- - Dashboard row-view logic is used: GM0 % = GP0 / Sales Budgeted Price.
-- - US benchmark GM0 is total US article GP0 / total US article Sales Budgeted Price over the same window.
-- - Article actual GM0 is computed as article GP0 / article Sales Budgeted Price.
-- - Source is the derived profitability table, which is already extracted from the consolidated GP goods view and includes item-level info.
-- ################
-- Check with the dashboard:
-- (put here if the number were checked in the main dashboard - to be filled manually)
-- ################
-- Scope:
-- - Retail Unit: US
-- - Window: 2026-05-01 to 2026-05-31
-- - Source table/view: `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
-- - Runner/Billing project: ingka-sot-isa-dev
-- - Dry-run cost (observed on derived source): 13,361,615,064 bytes (~13.36 GB)
--
-- Cost check command:
-- bq query --project_id=ingka-sot-isa-dev --use_legacy_sql=false --dry_run "$(sed -n '/^WITH /,$p' top_10_profit_potential_articles_last_30_days_store_274.sql)"

WITH base AS (
  SELECT
    item_no,
    SUM(gross_profit_gp0_amount) AS gp0,
    SUM(total_delivered_sales_net_amount) AS dns,
    SUM(total_bud_sales_amount) AS budget_sales
  FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
  WHERE retail_unit_code = 'US'
    AND item_no IS NOT NULL
    AND transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31'
  GROUP BY item_no
),
benchmark AS (
  SELECT
    SAFE_DIVIDE(SUM(gp0), SUM(budget_sales)) AS us_benchmark_gm0_ratio
  FROM base
  WHERE budget_sales > 0
)
SELECT
  b.item_no,
  ROUND(b.dns / 1000, 0) AS dns_k,
  ROUND(b.budget_sales / 1000, 0) AS budget_sales_k,
  ROUND(b.gp0 / 1000, 0) AS gp0_k,
  ROUND(100 * SAFE_DIVIDE(b.gp0, b.budget_sales), 2) AS actual_gm0_pct,
  ROUND(100 * bm.us_benchmark_gm0_ratio, 2) AS us_benchmark_gm0_pct,
  ROUND(((bm.us_benchmark_gm0_ratio * b.budget_sales) - b.gp0) / 1000, 0) AS gp0_potential_k
FROM base b
CROSS JOIN benchmark bm
WHERE b.budget_sales > 0
  AND SAFE_DIVIDE(b.gp0, b.budget_sales) < bm.us_benchmark_gm0_ratio
  AND (bm.us_benchmark_gm0_ratio * b.budget_sales) - b.gp0 > 0
ORDER BY gp0_potential_k DESC
LIMIT 10;

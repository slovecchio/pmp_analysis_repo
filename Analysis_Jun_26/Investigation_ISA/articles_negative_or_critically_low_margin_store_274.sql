-- ################
-- Initial Question:
-- "Which articles have negative or critically low margin?"
-- ################
-- Revised Question:
-- Which articles in US stores have negative or critically low GM0 from 2026-05-01 to 2026-05-31?
-- ################
-- Answer:
-- Top 10 results, ordered by lowest GM0 %.
-- Query run date: 2026-07-17.
--
-- item_no  | gp0_k | dns_k | budget_sales_k | gm0_pct | gm0_flag
-- 00570401 | -4    | 2     | 4              | -92.70  | negative_gm0
-- 20521693 | -332  | 402   | 364            | -91.03  | negative_gm0
-- 20466682 | -305  | 418   | 420            | -72.64  | negative_gm0
-- 90546478 | -84   | 149   | 138            | -60.90  | negative_gm0
-- 40599596 | -3    | 2     | 5              | -57.29  | negative_gm0
-- 40493420 | -263  | 491   | 460            | -57.16  | negative_gm0
-- 30546508 | -263  | 622   | 501            | -52.63  | negative_gm0
-- 10493520 | -325  | 758   | 619            | -52.48  | negative_gm0
-- 50462135 | -370  | 328   | 754            | -49.03  | negative_gm0
-- 10510421 | 0     | 1     | 1              | -48.91  | negative_gm0
-- ################
-- Assumptions/Doubts:
-- - Retail Unit US is used.
-- - The window starts on 2026-05-01 and ends on 2026-05-31.
-- - Dashboard row-view logic is used: GM0 % = GP0 / Sales Budgeted Price.
-- - Negative GM0 means GM0 < 0%.
-- - Critically low GM0 means GM0 >= 0% and < 10%.
-- - Source is the derived profitability table, which is already extracted from the consolidated GP goods view and includes item-level info.
-- - No minimum Sales Budgeted Price threshold is applied beyond budget_sales > 0, so very small budget sales values can create extreme GM0 percentages.
-- ################
-- Check with the dashboard:
-- (put here if the number were checked in the main dashboard - to be filled manually)
-- ################
-- Scope:
-- - Retail Unit: US
-- - Window: 2026-05-01 to 2026-05-31
-- - Source table/view: `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
-- - Runner/Billing project: ingka-sot-isa-dev
-- - Dry-run cost (observed on derived source): 17,320,612,120 bytes (~17.32 GB)
--
-- Cost check command:
-- bq query --project_id=ingka-sot-isa-dev --use_legacy_sql=false --dry_run "$(sed -n '/^WITH /,$p' articles_negative_or_critically_low_margin_store_274.sql)"

WITH base AS (
  SELECT
    item_no,
    SUM(gross_profit_gp0_amount) AS gp0,
    SUM(total_bud_sales_amount) AS budget_sales,
    SUM(total_delivered_sales_net_amount) AS dns
  FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
  WHERE retail_unit_code = 'US'
    AND item_no IS NOT NULL
    AND transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31'
  GROUP BY item_no
)
SELECT
  item_no,
  ROUND(gp0 / 1000, 0) AS gp0_k,
  ROUND(dns / 1000, 0) AS dns_k,
  ROUND(budget_sales / 1000, 0) AS budget_sales_k,
  ROUND(100 * SAFE_DIVIDE(gp0, budget_sales), 2) AS gm0_pct,
  CASE
    WHEN SAFE_DIVIDE(gp0, budget_sales) < 0 THEN 'negative_gm0'
    WHEN SAFE_DIVIDE(gp0, budget_sales) < 0.10 THEN 'critically_low_gm0'
    ELSE 'ok'
  END AS gm0_flag
FROM base
WHERE budget_sales > 0
  AND SAFE_DIVIDE(gp0, budget_sales) < 0.10
ORDER BY gm0_pct ASC, gp0_k ASC
LIMIT 10;

-- ################
-- Initial Question: 
-- "What is my store's gross margin today vs target?"
-- ################
-- Revised Question:
-- What is each US store's GM0, GM1 and GM2 from 2026-05-01 to 2026-05-31?
-- ################
-- Answer: 
-- Top 10 results, ordered by lowest GM0 %, from 2026-05-01 to 2026-05-31.
-- Query run date: 2026-07-17.
--
-- store_no | as_of_date | dns_k | budget_sales_k | gp0_k | gp1_k | gp2_k | gm0_pct | gm1_pct | gm2_pct
-- 1130     | 2026-05-31 | -64   | -82            | -28   | -15   | -895  | 33.88   | 22.83   | 1409.13
-- 162      | 2026-05-31 | 76117 | 72866          | 31696 | 37243 | 34224 | 43.50   | 48.93   | 44.96
-- 1147     | 2026-05-31 | 6209  | 6025           | 2635  | 3077  | 2951  | 43.73   | 49.56   | 47.52
-- 535      | 2026-05-31 | 60269 | 58971          | 25820 | 28960 | 26968 | 43.78   | 48.05   | 44.75
-- 411      | 2026-05-31 | 126270| 124218         | 54414 | 61318 | 58080 | 43.80   | 48.56   | 46.00
-- 488      | 2026-05-31 | 169521| 166806         | 73495 | 81773 | 77700 | 44.06   | 48.24   | 45.83
-- 536      | 2026-05-31 | 70831 | 69689          | 30845 | 34475 | 32553 | 44.26   | 48.67   | 45.96
-- 1100     | 2026-05-31 | 9494  | 9028           | 3996  | 4853  | 4406  | 44.27   | 51.11   | 46.40
-- 215      | 2026-05-31 | 69857 | 67230          | 29772 | 34605 | 31785 | 44.28   | 49.54   | 45.50
-- 511      | 2026-05-31 | 78969 | 75567          | 33576 | 39723 | 37999 | 44.43   | 50.30   | 48.12

-- ################
-- Assumptions/Doubts: 
-- - Dashboard row-view logic is used for margin percentages.
-- - GM0 % = GP0 / Sales Budgeted Price.
-- - GM1 % = GP1 / Delivered Net Sales.
-- - GM2 % = GP2 / Delivered Net Sales.
-- - Source is the derived profitability table, which is already extracted from the consolidated GP goods view and includes item-level info used by other queries.
-- ################
-- Check with the dashboard: 
-- (put here if the number where checked in the main dashboard - to be filled manually)
-- ################
-- Scope:
-- - Retail Unit: US
-- - Window: 2026-05-01 to 2026-05-31
-- - Metric interpretation:
--   actual GM0 % = GP0 / Sales Budgeted Price
--   actual GM1 % = GP1 / Delivered Net Sales
--   actual GM2 % = GP2 / Delivered Net Sales
--
-- Source table/view:
-- `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
--


WITH base AS (
  SELECT
    store_no,
    MAX(transaction_date) AS as_of_date,
    SUM(gross_profit_gp0_amount) AS gp0_actual,
    SUM(gross_profit_gp1_amount) AS gp1_actual,
    SUM(gross_profit_gp2_amount) AS gp2_actual,
    SUM(total_delivered_sales_net_amount) AS dns_actual,
    SUM(total_bud_sales_amount) AS bud_sales
  FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
  WHERE retail_unit_code = 'US'
    AND transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31'
  GROUP BY store_no
)
SELECT
  store_no,
  as_of_date,
  ROUND(dns_actual / 1000, 0) AS dns_k,
  ROUND(bud_sales / 1000, 0) AS budget_sales_k,
  ROUND(gp0_actual / 1000, 0) AS gp0_k,
  ROUND(gp1_actual / 1000, 0) AS gp1_k,
  ROUND(gp2_actual / 1000, 0) AS gp2_k,
  ROUND(100 * SAFE_DIVIDE(gp0_actual, bud_sales), 2) AS gm0_pct,
  ROUND(100 * SAFE_DIVIDE(gp1_actual, dns_actual), 2) AS gm1_pct,
  ROUND(100 * SAFE_DIVIDE(gp2_actual, dns_actual), 2) AS gm2_pct
FROM base
ORDER BY gm0_pct ASC;

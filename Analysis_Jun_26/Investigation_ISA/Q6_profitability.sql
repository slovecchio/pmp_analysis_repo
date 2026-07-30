-- ################
-- Initial Question:
-- "How profitable was the US business in May?"
-- ################
-- Revised Question:
-- What were total DNS, budget sales, GP0, GP1, GP2, GM0, GM1 and GM2 for US stores from 2026-05-01 to 2026-05-31?
-- ################
-- Answer:
-- Query run date: 2026-07-30.
--
-- dns_k  | budget_sales_k | gp0_k  | gp1_k  | gp2_k  | gm0_pct | gm1_pct | gm2_pct
-- 421888 | 413593         | 198766 | 215000 | 205487 | 48.06   | 50.96   | 48.71
-- ################
-- Assumptions/Doubts:
-- - Retail Unit US is used.
-- - The window starts on 2026-05-01 and ends on 2026-05-31.
-- - Dashboard row-view logic is used for margin percentages.
-- - GM0 % = GP0 / Sales Budgeted Price.
-- - GM1 % = GP1 / Delivered Net Sales.
-- - GM2 % = GP2 / Delivered Net Sales.
-- ################
-- Scope:
-- - Retail Unit: US
-- - Window: 2026-05-01 to 2026-05-31
-- - Source table/view: `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
-- - Runner/Billing project: ingka-sot-isa-dev

WITH base AS (
  SELECT
    SUM(total_delivered_sales_net_amount) AS dns,
    SUM(total_bud_sales_amount) AS budget_sales,
    SUM(gross_profit_gp0_amount) AS gp0,
    SUM(gross_profit_gp1_amount) AS gp1,
    SUM(gross_profit_gp2_amount) AS gp2
  FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
  WHERE retail_unit_code = 'US'
    AND transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31'
)
SELECT
  ROUND(dns / 1000, 0) AS dns_k,
  ROUND(budget_sales / 1000, 0) AS budget_sales_k,
  ROUND(gp0 / 1000, 0) AS gp0_k,
  ROUND(gp1 / 1000, 0) AS gp1_k,
  ROUND(gp2 / 1000, 0) AS gp2_k,
  ROUND(100 * SAFE_DIVIDE(gp0, budget_sales), 2) AS gm0_pct,
  ROUND(100 * SAFE_DIVIDE(gp1, dns), 2) AS gm1_pct,
  ROUND(100 * SAFE_DIVIDE(gp2, dns), 2) AS gm2_pct
FROM base;
-- ################
-- Initial Question:
-- "What is monthly profitability for the current fiscal year?"
-- ################
-- Revised Question:
-- What are monthly GP0, GP1, GP2, GM0, GM1 and GM2 for US, by month in the current fiscal year from September 2025 to May 2026?
-- ################
-- Answer:
-- Query run date: 2026-07-30.
--
-- month      | gp0_k  | gp1_k  | gp2_k  | gm0_pct | gm1_pct | gm2_pct
-- 2025-09-01 | 184521 | 199237 | 186503 | 46.27   | 49.00   | 45.86
-- 2025-10-01 | 179449 | 202530 | 191751 | 47.35   | 51.04   | 48.32
-- 2025-11-01 | 189153 | 206060 | 197208 | 47.20   | 50.02   | 47.87
-- 2025-12-01 | 185317 | 198224 | 189049 | 47.00   | 49.27   | 46.98
-- 2026-01-01 | 194428 | 208312 | 197145 | 47.11   | 49.12   | 46.49
-- 2026-02-01 | 164575 | 177693 | 169575 | 48.04   | 50.17   | 47.88
-- 2026-03-01 | 183922 | 198982 | 188375 | 47.76   | 49.90   | 47.24
-- 2026-04-01 | 173293 | 186957 | 178299 | 48.30   | 50.32   | 47.99
-- 2026-05-01 | 198766 | 215000 | 205487 | 48.06   | 50.96   | 48.71
-- ################
-- Assumptions/Doubts:
-- - Retail Unit US is used.
-- - Current fiscal year is interpreted as 2025-09-01 to 2026-05-31, as requested.
-- - Results are aggregated by calendar month within that fiscal-year window.
-- - GP0, GP1 and GP2 are summed directly.
-- - GM0 % = GP0 / Sales Budgeted Price.
-- - GM1 % = GP1 / Delivered Net Sales.
-- - GM2 % = GP2 / Delivered Net Sales.
-- ################
-- Scope:
-- - Retail Unit: US
-- - Window: 2025-09-01 to 2026-05-31
-- - Grain: month
-- - Source table/view: `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
-- - Runner/Billing project: ingka-sot-isa-dev

SELECT
  DATE_TRUNC(transaction_date, MONTH) AS month,
  ROUND(SUM(gross_profit_gp0_amount) / 1000, 0) AS gp0_k,
  ROUND(SUM(gross_profit_gp1_amount) / 1000, 0) AS gp1_k,
  ROUND(SUM(gross_profit_gp2_amount) / 1000, 0) AS gp2_k,
  ROUND(
    100 * SAFE_DIVIDE(
      SUM(gross_profit_gp0_amount),
      SUM(total_bud_sales_amount)
    ),
    2
  ) AS gm0_pct,
  ROUND(
    100 * SAFE_DIVIDE(
      SUM(gross_profit_gp1_amount),
      SUM(total_delivered_sales_net_amount)
    ),
    2
  ) AS gm1_pct,
  ROUND(
    100 * SAFE_DIVIDE(
      SUM(gross_profit_gp2_amount),
      SUM(total_delivered_sales_net_amount)
    ),
    2
  ) AS gm2_pct
FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
WHERE retail_unit_code = 'US'
  AND transaction_date BETWEEN DATE '2025-09-01' AND DATE '2026-05-31'
GROUP BY month
ORDER BY month;

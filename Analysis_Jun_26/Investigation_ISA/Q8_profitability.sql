-- ################
-- Initial Question:
-- "Which HFBs generate the most profit?"
-- ################
-- Revised Question:
-- Which HFBs generated the most GP0 in US stores from 2026-05-01 to 2026-05-31?
-- ################
-- Answer:
-- Top 10 results, ordered by GP0.
-- Query run date: 2026-07-30.
--
-- hfb_no | hfb_name                     | dns_k | gp0_k | gm0_pct
-- 04     | Bedroom furniture            | 72908 | 35889 | 50.71
-- 02     | Store and organise furniture | 55587 | 21748 | 42.04
-- 07     | Kitchen                      | 34403 | 21148 | 62.88
-- 01     | Living room seating          | 31881 | 15263 | 46.18
-- 05     | Beds & Mattresses            | 35374 | 13901 | 39.72
-- 03     | Workspaces                   | 22235 | 10774 | 47.60
-- 16     | Decoration                   | 17233 | 9790  | 54.70
-- 18     | Home organisation            | 19711 | 9588  | 51.21
-- 11     | Bed and bath textiles        | 20649 | 9234  | 45.82
-- 09     | Children's IKEA              | 16572 | 7586  | 46.36
-- ################
-- Assumptions/Doubts:
-- - HFB fields come from item-level fields in the derived profitability table.
-- - Retail Unit US is used.
-- - GP0 amount is used as the profit ranking metric.
-- - GM0 % = GP0 / Sales Budgeted Price.
-- ################
-- Scope:
-- - Retail Unit: US
-- - Window: 2026-05-01 to 2026-05-31
-- - Source table/view: `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
-- - Runner/Billing project: ingka-sot-isa-dev

SELECT
  HFB_no AS hfb_no,
  ANY_VALUE(HFB_name) AS hfb_name,
  ROUND(SUM(total_delivered_sales_net_amount) / 1000, 0) AS dns_k,
  ROUND(SUM(gross_profit_gp0_amount) / 1000, 0) AS gp0_k,
  ROUND(100 * SAFE_DIVIDE(SUM(gross_profit_gp0_amount), SUM(total_bud_sales_amount)), 2) AS gm0_pct
FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
WHERE retail_unit_code = 'US'
  AND transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31'
  AND HFB_no IS NOT NULL
GROUP BY HFB_no
ORDER BY gp0_k DESC
LIMIT 10;
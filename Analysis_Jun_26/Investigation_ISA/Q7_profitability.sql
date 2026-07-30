-- ################
-- Initial Question:
-- "Which stores sell the most?"
-- ################
-- Revised Question:
-- Which US stores had the highest Delivered Net Sales from 2026-05-01 to 2026-05-31, and what was their GM0?
-- ################
-- Answer:
-- Top 10 results, ordered by Delivered Net Sales.
-- Query run date: 2026-07-30.
--
-- store_no | store_name                         | dns_k  | gp0_k | gm0_pct
-- 159      | IKEA eCommerce US                  | 162138 | 77514 | 48.70
-- 488      | IKEA Seattle - Renton              | 9074   | 4139  | 46.89
-- 399      | IKEA Los Angeles - Burbank         | 8934   | 4191  | 48.03
-- 028      | IKEA Oregon - Portland             | 7761   | 3616  | 47.99
-- 158      | IKEA Boston - Stoughton            | 7445   | 3516  | 46.88
-- 921      | IKEA New York - Brooklyn           | 7082   | 3307  | 48.05
-- 347      | IKEA San Francisco - East Palo Alto| 6862   | 3137  | 47.01
-- 210      | IKEA Chicago - Schaumburg          | 6839   | 3214  | 47.82
-- 064      | IKEA Denver - Centennial           | 6806   | 3145  | 47.76
-- 166      | IKEA San Diego                     | 6649   | 3117  | 47.77
-- ################
-- Assumptions/Doubts:
-- - Delivered Net Sales is used as the sales ranking metric.
-- - Retail Unit US is used.
-- - GM0 % = GP0 / Sales Budgeted Price.
-- ################
-- Scope:
-- - Retail Unit: US
-- - Window: 2026-05-01 to 2026-05-31
-- - Source table/view: `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
-- - Runner/Billing project: ingka-sot-isa-dev

SELECT
  store_no,
  ANY_VALUE(bu_name) AS store_name,
  ROUND(SUM(total_delivered_sales_net_amount) / 1000, 0) AS dns_k,
  ROUND(SUM(gross_profit_gp0_amount) / 1000, 0) AS gp0_k,
  ROUND(100 * SAFE_DIVIDE(SUM(gross_profit_gp0_amount), SUM(total_bud_sales_amount)), 2) AS gm0_pct
FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
WHERE retail_unit_code = 'US'
  AND transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31'
GROUP BY store_no
ORDER BY dns_k DESC
LIMIT 10;
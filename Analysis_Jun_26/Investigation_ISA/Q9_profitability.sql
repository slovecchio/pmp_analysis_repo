-- The top 10 US items with the highest GP0 year-over-year increase comparing May 2026 with May 2025 are shown below, with item number, item name, Delivered Net Sales, GP0, GP0 YoY change, GM0 by year, and GM0 YoY change in percentage points.

WITH item_month AS (
  SELECT
    item_no,
    ANY_VALUE(item_name) AS item_name,
    EXTRACT(YEAR FROM transaction_date) AS year,
    SUM(total_delivered_sales_net_amount) AS dns,
    SUM(total_bud_sales_amount) AS budget_sales,
    SUM(gross_profit_gp0_amount) AS gp0
  FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
  WHERE retail_unit_code = 'US'
    AND transaction_date BETWEEN DATE '2025-05-01' AND DATE '2026-05-31'
    AND EXTRACT(MONTH FROM transaction_date) = 5
    AND item_no IS NOT NULL
  GROUP BY item_no, year
),
pivoted AS (
  SELECT
    item_no,
    ANY_VALUE(item_name) AS item_name,
    SUM(IF(year = 2025, dns, 0)) AS dns_2025,
    SUM(IF(year = 2026, dns, 0)) AS dns_2026,
    SUM(IF(year = 2025, budget_sales, 0)) AS budget_sales_2025,
    SUM(IF(year = 2026, budget_sales, 0)) AS budget_sales_2026,
    SUM(IF(year = 2025, gp0, 0)) AS gp0_2025,
    SUM(IF(year = 2026, gp0, 0)) AS gp0_2026
  FROM item_month
  GROUP BY item_no
)
SELECT
  item_no,
  item_name,
  ROUND(dns_2025 / 1000, 0) AS dns_2025_k,
  ROUND(dns_2026 / 1000, 0) AS dns_2026_k,
  ROUND(gp0_2025 / 1000, 0) AS gp0_2025_k,
  ROUND(gp0_2026 / 1000, 0) AS gp0_2026_k,
  ROUND((gp0_2026 - gp0_2025) / 1000, 0) AS gp0_yoy_change_k,
  ROUND(100 * SAFE_DIVIDE(gp0_2025, budget_sales_2025), 2) AS gm0_2025_pct,
  ROUND(100 * SAFE_DIVIDE(gp0_2026, budget_sales_2026), 2) AS gm0_2026_pct,
  ROUND(100 * SAFE_DIVIDE(gp0_2026, budget_sales_2026) - 100 * SAFE_DIVIDE(gp0_2025, budget_sales_2025), 2) AS gm0_yoy_change_pct_points
FROM pivoted
WHERE dns_2025 >= 100000
  AND dns_2026 >= 100000
  AND budget_sales_2025 > 0
  AND budget_sales_2026 > 0
ORDER BY gp0_yoy_change_k DESC
LIMIT 10;
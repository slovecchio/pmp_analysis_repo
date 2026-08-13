-- The US articles with negative or critically low GM0 from 2026-05-01 to 2026-05-31 are shown below, ordered by lowest GM0 %, with item number, item name, GP0 in thousands, Delivered Net Sales in thousands, budget sales in thousands, GM0 percentage, and margin flag.

WITH base AS (
  SELECT
    item_no,
    item_name,
    SUM(gross_profit_gp0_amount) AS gp0,
    SUM(total_bud_sales_amount) AS budget_sales,
    SUM(total_delivered_sales_net_amount) AS dns
  FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
  WHERE retail_unit_code = 'US'
    AND item_no IS NOT NULL
    AND transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31'
  GROUP BY item_no, item_name
)
SELECT
  item_no,
  item_name,
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
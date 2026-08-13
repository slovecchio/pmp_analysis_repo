-- The US business profitability from 2026-05-01 to 2026-05-31 is shown below, with Delivered Net Sales, budget sales, GP0, GP1 and GP2 in thousands, plus GM0, GM1 and GM2 percentages.

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
-- The US stores' GM0, GM1 and GM2 from 2026-05-01 to 2026-05-31 are shown below, ordered by lowest GM0 %, with store number, store name, GP0/GP1/GP2 in thousands, and GM0/GM1/GM2 percentages.

WITH base AS (
  SELECT
    store_no,
    bu_name,
    SUM(gross_profit_gp0_amount) AS gp0_actual,
    SUM(gross_profit_gp1_amount) AS gp1_actual,
    SUM(gross_profit_gp2_amount) AS gp2_actual,
    SUM(total_delivered_sales_net_amount) AS dns_actual,
    SUM(total_bud_sales_amount) AS bud_sales
  FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
  WHERE retail_unit_code = 'US'
    AND transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31'
  GROUP BY store_no, bu_name
)
SELECT
  store_no,
  bu_name,
  ROUND(gp0_actual / 1000, 0) AS gp0_k,
  ROUND(gp1_actual / 1000, 0) AS gp1_k,
  ROUND(gp2_actual / 1000, 0) AS gp2_k,
  ROUND(100 * SAFE_DIVIDE(gp0_actual, bud_sales), 2) AS gm0_pct,
  ROUND(100 * SAFE_DIVIDE(gp1_actual, dns_actual), 2) AS gm1_pct,
  ROUND(100 * SAFE_DIVIDE(gp2_actual, dns_actual), 2) AS gm2_pct
FROM base
ORDER BY gm0_pct ASC;
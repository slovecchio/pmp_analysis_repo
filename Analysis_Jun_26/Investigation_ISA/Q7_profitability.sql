-- The top 10 US stores by Delivered Net Sales from 2026-05-01 to 2026-05-31 are shown below, with store number, store name, Delivered Net Sales in thousands, GP0 in thousands, and GM0 percentage.

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
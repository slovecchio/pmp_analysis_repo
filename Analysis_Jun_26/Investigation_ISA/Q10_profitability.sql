-- The monthly US profitability from September 2025 to May 2026 is shown below, with month, GP0, GP1 and GP2 in thousands, plus GM0, GM1 and GM2 percentages.

SELECT
  DATE_TRUNC(transaction_date, MONTH) AS month,
  ROUND(SUM(gross_profit_gp0_amount) / 1000, 0) AS gp0_k,
  ROUND(SUM(gross_profit_gp1_amount) / 1000, 0) AS gp1_k,
  ROUND(SUM(gross_profit_gp2_amount) / 1000, 0) AS gp2_k,
  ROUND(100 * SAFE_DIVIDE(SUM(gross_profit_gp0_amount), SUM(total_bud_sales_amount)), 2) AS gm0_pct,
  ROUND(100 * SAFE_DIVIDE(SUM(gross_profit_gp1_amount), SUM(total_delivered_sales_net_amount)), 2) AS gm1_pct,
  ROUND(100 * SAFE_DIVIDE(SUM(gross_profit_gp2_amount), SUM(total_delivered_sales_net_amount)), 2) AS gm2_pct
FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
WHERE retail_unit_code = 'US'
  AND transaction_date BETWEEN DATE '2025-09-01' AND DATE '2026-05-31'
GROUP BY month
ORDER BY month;
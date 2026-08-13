-- The top 10 US HFBs by GP0 from 2026-05-01 to 2026-05-31 are shown below, with HFB number, HFB name, Delivered Net Sales in thousands, GP0 in thousands, and GM0 percentage.

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
-- The top 10 most profitable US articles for the last 7 days, last 30 days and May 2026 are shown below, with period, item number, item name, GP0 in thousands, Delivered Net Sales in thousands, and GM0 percentage.

WITH item_metrics AS (
  SELECT
    item_no,
    item_name,
    SUM(IF(transaction_date BETWEEN DATE '2026-05-25' AND DATE '2026-05-31', gross_profit_gp0_amount, 0)) AS gp0_7d,
    SUM(IF(transaction_date BETWEEN DATE '2026-05-25' AND DATE '2026-05-31', total_delivered_sales_net_amount, 0)) AS dns_7d,
    SUM(IF(transaction_date BETWEEN DATE '2026-05-25' AND DATE '2026-05-31', total_bud_sales_amount, 0)) AS budget_sales_7d,
    SUM(IF(transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31', gross_profit_gp0_amount, 0)) AS gp0_30d,
    SUM(IF(transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31', total_delivered_sales_net_amount, 0)) AS dns_30d,
    SUM(IF(transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31', total_bud_sales_amount, 0)) AS budget_sales_30d,
    SUM(gross_profit_gp0_amount) AS gp0_ytd,
    SUM(total_delivered_sales_net_amount) AS dns_ytd,
    SUM(total_bud_sales_amount) AS budget_sales_ytd
  FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
  WHERE retail_unit_code = 'US'
    AND item_no IS NOT NULL
    AND transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31'
  GROUP BY item_no, item_name
),
ranked AS (
  SELECT 'last_7_days' AS period, item_no, item_name, gp0_7d AS gp0, dns_7d AS dns, budget_sales_7d AS budget_sales FROM item_metrics
  UNION ALL
  SELECT 'last_30_days' AS period, item_no, item_name, gp0_30d AS gp0, dns_30d AS dns, budget_sales_30d AS budget_sales FROM item_metrics
  UNION ALL
  SELECT 'may_2026' AS period, item_no, item_name, gp0_ytd AS gp0, dns_ytd AS dns, budget_sales_ytd AS budget_sales FROM item_metrics
)
SELECT
  period,
  item_no,
  item_name,
  ROUND(gp0 / 1000, 0) AS gp0_k,
  ROUND(dns / 1000, 0) AS dns_k,
  ROUND(100 * SAFE_DIVIDE(gp0, budget_sales), 2) AS gm0_pct
FROM ranked
WHERE gp0 > 0
  AND budget_sales > 0
QUALIFY ROW_NUMBER() OVER (PARTITION BY period ORDER BY gp0 DESC) <= 10
ORDER BY period, gp0_k DESC;
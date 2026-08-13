-- The top 10 US articles with the highest GP0 potential from 2026-05-01 to 2026-05-31 are shown below, with item number, item name, Delivered Net Sales in thousands, budget sales in thousands, article GP0 in thousands, expected GP0 at the US GM0 benchmark in thousands, article GM0 %, US benchmark GM0 %, and GP0 potential in thousands.

WITH article_profitability AS (
  SELECT
    item_no,
    ANY_VALUE(item_name) AS item_name,
    SUM(total_delivered_sales_net_amount) AS delivered_net_sales,
    SUM(total_bud_sales_amount) AS budget_sales,
    SUM(gross_profit_gp0_amount) AS article_gp0
  FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
  WHERE retail_unit_code = 'US'
    AND transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31'
    AND item_no IS NOT NULL
  GROUP BY item_no
  HAVING budget_sales > 0
),
us_benchmark AS (
  SELECT
    SAFE_DIVIDE(SUM(article_gp0), SUM(budget_sales)) AS us_gm0_ratio
  FROM article_profitability
),
article_gap AS (
  SELECT
    a.item_no,
    a.item_name,
    a.delivered_net_sales,
    a.budget_sales,
    a.article_gp0,
    b.us_gm0_ratio * a.budget_sales AS us_benchmark_gp0,
    (b.us_gm0_ratio * a.budget_sales) - a.article_gp0 AS gp0_potential
  FROM article_profitability a
  CROSS JOIN us_benchmark b
)
SELECT
  item_no,
  item_name,
  ROUND(delivered_net_sales / 1000, 0) AS dns_k,
  ROUND(budget_sales / 1000, 0) AS budget_sales_k,
  ROUND(article_gp0 / 1000, 0) AS article_gp0_k,
  ROUND(us_benchmark_gp0 / 1000, 0) AS us_benchmark_gp0_k,
  ROUND(100 * SAFE_DIVIDE(article_gp0, budget_sales), 2) AS article_gm0_pct,
  ROUND(100 * SAFE_DIVIDE(us_benchmark_gp0, budget_sales), 2) AS us_benchmark_gm0_pct,
  ROUND(gp0_potential / 1000, 0) AS gp0_potential_k
FROM article_gap
WHERE gp0_potential > 0
ORDER BY gp0_potential DESC
LIMIT 10;
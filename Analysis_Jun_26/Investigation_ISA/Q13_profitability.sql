-- The HFBs in store 488 with strong sales and low gross margin from 2026-05-01 to 2026-05-31 are shown below, with store number, HFB number, HFB name, Created Net Sales by year in thousands, Created Net Sales index vs last year, GP0 and budget sales in thousands, GM0 %, store-average HFB GM0 %, and GM0 gap in percentage points.

WITH created_sales AS (
  SELECT
    store_no,
    HFB_no AS hfb_no,
    ANY_VALUE(HFB_name) AS hfb_name,
    SUM(IF(transaction_date BETWEEN DATE '2025-05-01' AND DATE '2025-05-31', created_sales_net_amount, 0)) AS created_net_sales_2025,
    SUM(IF(transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31', created_sales_net_amount, 0)) AS created_net_sales_2026
  FROM `ingka-sot-isa-dev.isa_derived.derived_common_sales`
  WHERE retail_unit_code = 'US'
    AND store_no = '488'
    AND transaction_date BETWEEN DATE '2025-05-01' AND DATE '2026-05-31'
    AND EXTRACT(MONTH FROM transaction_date) = 5
    AND item_no IS NOT NULL
    AND HFB_no IS NOT NULL
  GROUP BY store_no, HFB_no
),
sales_metrics AS (
  SELECT
    store_no,
    hfb_no,
    hfb_name,
    created_net_sales_2025,
    created_net_sales_2026,
    100 * SAFE_DIVIDE(created_net_sales_2026, created_net_sales_2025) AS created_net_sales_index_vs_ly
  FROM created_sales
  WHERE created_net_sales_2025 > 0
    AND created_net_sales_2026 > 0
),
profitability AS (
  SELECT
    store_no,
    HFB_no AS hfb_no,
    SUM(total_bud_sales_amount) AS budget_sales_amount,
    SUM(gross_profit_gp0_amount) AS gp0_amount,
    SAFE_DIVIDE(SUM(gross_profit_gp0_amount), SUM(total_bud_sales_amount)) AS gm0_ratio
  FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
  WHERE retail_unit_code = 'US'
    AND store_no = '488'
    AND transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31'
    AND item_no IS NOT NULL
    AND HFB_no IS NOT NULL
  GROUP BY store_no, HFB_no
  HAVING budget_sales_amount > 0
),
benchmarks AS (
  SELECT
    AVG(gm0_ratio) AS avg_hfb_gm0_ratio
  FROM profitability
),
combined AS (
  SELECT
    s.store_no,
    s.hfb_no,
    s.hfb_name,
    s.created_net_sales_2025,
    s.created_net_sales_2026,
    s.created_net_sales_index_vs_ly,
    p.gp0_amount,
    p.budget_sales_amount,
    p.gm0_ratio
  FROM sales_metrics s
  INNER JOIN profitability p
    USING (store_no, hfb_no)
)
SELECT
  c.store_no,
  c.hfb_no,
  c.hfb_name,
  ROUND(c.created_net_sales_2025 / 1000, 0) AS created_net_sales_2025_k,
  ROUND(c.created_net_sales_2026 / 1000, 0) AS created_net_sales_2026_k,
  ROUND(c.created_net_sales_index_vs_ly, 2) AS created_net_sales_index_vs_ly,
  ROUND(c.gp0_amount / 1000, 0) AS gp0_k,
  ROUND(c.budget_sales_amount / 1000, 0) AS budget_sales_k,
  ROUND(100 * c.gm0_ratio, 2) AS gm0_pct,
  ROUND(100 * b.avg_hfb_gm0_ratio, 2) AS avg_hfb_gm0_pct,
  ROUND(100 * (c.gm0_ratio - b.avg_hfb_gm0_ratio), 2) AS gm0_gap_pct_points
FROM combined c
CROSS JOIN benchmarks b
WHERE c.created_net_sales_index_vs_ly > 110
  AND c.gm0_ratio < b.avg_hfb_gm0_ratio
ORDER BY c.created_net_sales_index_vs_ly DESC, c.gm0_ratio ASC;-- ################

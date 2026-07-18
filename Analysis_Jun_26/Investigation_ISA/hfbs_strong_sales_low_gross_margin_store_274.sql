-- ################
-- Initial Question:
-- "Which HFBs have strong sales but low gross margin?"
-- ################
-- Revised Question:
-- Which item-level HFBs in US stores have strong Delivered Net Sales and below-average GM0 from 2026-05-01 to 2026-05-31?
-- ################
-- Answer:
-- Query returned 5 HFBs matching the criteria.
-- Query run date: 2026-07-17.
--
-- hfb_no | hfb_name                         | delivered_net_sales_k | gp0_k  | gm0_pct | avg_hfb_gm0_pct | gm0_gap_pct_points | sales_rank | low_gm0_rank
-- 02     | Store and organise furniture     | 1739116               | 656734 | 39.98   | 45.15           | -5.17               | 1          | 5
-- 18     | Home organisation                | 471167                | 197374 | 44.16   | 45.15           | -0.99               | 6          | 12
-- 05     | Beds & Mattresses                | 464287                | 195023 | 41.99   | 45.15           | -3.16               | 7          | 7
-- 01     | Living room seating              | 458464                | 207907 | 44.14   | 45.15           | -1.00               | 8          | 11
-- 10     | Lighting & Home electronics      | 354403                | 125273 | 37.14   | 45.15           | -8.00               | 9          | 2
-- ################
-- Assumptions/Doubts:
-- - Retail Unit US is used.
-- - The window starts on 2026-05-01 and ends on 2026-05-31.
-- - Strong sales means HFB Delivered Net Sales at or above the 70th percentile across HFBs.
-- - Low gross margin means HFB GM0 is below the simple average GM0 across HFBs.
-- - Dashboard row-view logic is used for GM0 %: GP0 / Sales Budgeted Price.
-- - Source is the derived profitability table, which is already extracted from the consolidated GP goods view and includes item-level HFB info.
-- ################
-- Check with the dashboard:
-- (put here if the number were checked in the main dashboard - to be filled manually)
-- ################
-- Scope:
-- - Retail Unit: US
-- - Window: 2026-05-01 to 2026-05-31
-- - HFB granularity: item-level HFB fields from the derived profitability table
-- - Source table/view: `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
-- - Runner/Billing project: ingka-sot-isa-dev
-- - Dry-run cost (observed on derived source): 18,486,021,158 bytes (~18.49 GB)
--
-- Cost check command:
-- bq query --project_id=ingka-sot-isa-dev --use_legacy_sql=false --dry_run "$(sed -n '/^WITH /,$p' hfbs_strong_sales_low_gross_margin_store_274.sql)"

WITH base AS (
  -- Step 1: Aggregate Delivered Net Sales and GP0 per item-level HFB
  SELECT
    home_furnishing_business_no AS hfb_no,
    home_furnishing_business_name AS hfb_name,
    SUM(total_delivered_sales_net_amount) AS dns_amount,  -- Gross Sales minus Returns
    SUM(total_bud_sales_amount) AS budget_sales_amount,   -- dashboard GM0 denominator
    SUM(gross_profit_gp0_amount) AS gp0_amount            -- GP0 = Budgeted Sales - Budgeted COGS
  FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
  WHERE retail_unit_code = 'US'
    AND transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31'
    AND item_no IS NOT NULL
    AND home_furnishing_business_no IS NOT NULL           -- require item-level HFB
  GROUP BY 1, 2
),
metrics AS (
  -- Step 2: Compute GM0 ratio per HFB: GP0 / Sales Budgeted Price
  SELECT
    hfb_no,
    hfb_name,
    dns_amount,
    budget_sales_amount,
    gp0_amount,
    SAFE_DIVIDE(gp0_amount, budget_sales_amount) AS gm0_ratio -- dashboard row-view GM0 definition
  FROM base
  WHERE budget_sales_amount > 0  -- exclude HFBs where GM0 denominator is zero
),
thresholds AS (
  -- Step 3: Compute benchmark values across all HFBs
  --   strong_sales_threshold: 70th percentile of DNS (top 30% = strong sales)
  --   avg_gm0_ratio: simple average GM0 across all HFBs
  SELECT
    APPROX_QUANTILES(dns_amount, 100)[OFFSET(70)] AS strong_sales_threshold,
    AVG(gm0_ratio) AS avg_gm0_ratio
  FROM metrics
),
ranked AS (
  -- Step 4: Add ranks before filtering so ranks are relative to all HFB buckets
  SELECT
    m.*,
    DENSE_RANK() OVER (ORDER BY dns_amount DESC) AS sales_rank,
    DENSE_RANK() OVER (ORDER BY gm0_ratio ASC) AS low_gm0_rank
  FROM metrics m
)
SELECT
  r.hfb_no,
  r.hfb_name,
  ROUND(r.dns_amount / 1000, 0) AS delivered_net_sales_k,   -- in thousands
  ROUND(r.gp0_amount / 1000, 0) AS gp0_k,                   -- in thousands
  ROUND(100 * r.gm0_ratio, 2) AS gm0_pct,                   -- GP0 / Sales Budgeted Price
  ROUND(100 * t.avg_gm0_ratio, 2) AS avg_hfb_gm0_pct,        -- benchmark: avg across HFBs
  ROUND((100 * r.gm0_ratio) - (100 * t.avg_gm0_ratio), 2) AS gm0_gap_pct_points, -- negative = below avg
  r.sales_rank,
  r.low_gm0_rank
FROM ranked r
CROSS JOIN thresholds t
WHERE r.dns_amount >= t.strong_sales_threshold  -- filter: strong sales only
  AND r.gm0_ratio < t.avg_gm0_ratio             -- filter: below-average GM0
ORDER BY sales_rank, low_gm0_rank;

-- ################
-- Initial Question:
-- "Which items improved profitability year over year?"
-- ################
-- Revised Question:
-- Which US items had the highest GP0 increase year over year, and how did their GM0 change, comparing May 2026 with May 2025?
-- ################
-- Answer:
-- Top 10 results, ordered by highest GP0 year-over-year increase.
-- Query run date: 2026-07-30.
--
-- item_no  | item_name                                      | dns_2025_k | dns_2026_k | gp0_2025_k | gp0_2026_k | gp0_yoy_change_k | gm0_2025_pct | gm0_2026_pct | gm0_yoy_change_pct_points
-- 60473548 | ALEX drawer ut 36x70 black-brown NN            | 590        | 1098       | 242        | 539        | 297              | 40.98        | 48.69        | 7.71
-- 20522046 | BILLY N4 bookcs 80x28x202 white                | 1261       | 2632       | 303        | 552        | 250              | 24.03        | 23.58        | -0.45
-- 10576191 | HEMNES NNN chest/8 drw 160x96 white stain NA   | 342        | 1142       | 127        | 323        | 196              | 37.15        | 29.38        | -7.77
-- 00528916 | JATTEBO 1,5-seat module w stor NA              | 358        | 524        | 160        | 339        | 179              | 44.51        | 61.78        | 17.27
-- 40588183 | PAX wall-mntd strg frame 100x58x236 grey-beige NA | 176     | 522        | 90         | 262        | 172              | 51.20        | 53.86        | 2.66
-- 10394558 | SONGESAND wardrobe 120x60x191 white NA         | 259        | 494        | 118        | 283        | 165              | 45.55        | 44.97        | -0.57
-- 60561248 | STORKLINTA chest/6 drw 140x48x75 whi/A/U-F NA | 1978       | 1911       | 733        | 886        | 153              | 41.88        | 45.61        | 3.72
-- 10508932 | BILLY bookcs 80x28x202 oak effect              | 226        | 580        | 54         | 187        | 133              | 24.22        | 35.81        | 11.59
-- 90528907 | JATTEBO 1-seat module w stor NA                | 180        | 324        | 87         | 220        | 133              | 47.93        | 64.44        | 16.51
-- 00559291 | STORKLINTA chest/3 drw 70x48x75 whi/A/U-F NA  | 807        | 739        | 140        | 266        | 126              | 20.63        | 35.30        | 14.67
-- ################
-- Assumptions/Doubts:
-- - Retail Unit US is used.
-- - May 2026 is compared with May 2025 to avoid seasonality from comparing different months.
-- - Items must have at least 100K Delivered Net Sales in both May 2025 and May 2026.
-- - GM0 % = GP0 / Sales Budgeted Price.
-- - GP0 year-over-year change is May 2026 GP0 minus May 2025 GP0.
-- ################
-- Scope:
-- - Retail Unit: US
-- - Window: May 2026 compared with May 2025
-- - Source table/view: `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
-- - Runner/Billing project: ingka-sot-isa-dev

WITH item_month AS (
  SELECT
    item_no,
    ANY_VALUE(item_name) AS item_name,
    EXTRACT(YEAR FROM transaction_date) AS year,
    SUM(total_delivered_sales_net_amount) AS dns,
    SUM(total_bud_sales_amount) AS budget_sales,
    SUM(gross_profit_gp0_amount) AS gp0
  FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
  WHERE retail_unit_code = 'US'
    AND transaction_date BETWEEN DATE '2025-05-01' AND DATE '2026-05-31'
    AND EXTRACT(MONTH FROM transaction_date) = 5
    AND item_no IS NOT NULL
  GROUP BY item_no, year
), pivoted AS (
  SELECT
    item_no,
    ANY_VALUE(item_name) AS item_name,
    SUM(IF(year = 2025, dns, 0)) AS dns_2025,
    SUM(IF(year = 2026, dns, 0)) AS dns_2026,
    SUM(IF(year = 2025, budget_sales, 0)) AS budget_sales_2025,
    SUM(IF(year = 2026, budget_sales, 0)) AS budget_sales_2026,
    SUM(IF(year = 2025, gp0, 0)) AS gp0_2025,
    SUM(IF(year = 2026, gp0, 0)) AS gp0_2026
  FROM item_month
  GROUP BY item_no
)
SELECT
  item_no,
  item_name,
  ROUND(dns_2025 / 1000, 0) AS dns_2025_k,
  ROUND(dns_2026 / 1000, 0) AS dns_2026_k,
  ROUND(gp0_2025 / 1000, 0) AS gp0_2025_k,
  ROUND(gp0_2026 / 1000, 0) AS gp0_2026_k,
  ROUND((gp0_2026 - gp0_2025) / 1000, 0) AS gp0_yoy_change_k,
  ROUND(100 * SAFE_DIVIDE(gp0_2025, budget_sales_2025), 2) AS gm0_2025_pct,
  ROUND(100 * SAFE_DIVIDE(gp0_2026, budget_sales_2026), 2) AS gm0_2026_pct,
  ROUND(100 * SAFE_DIVIDE(gp0_2026, budget_sales_2026) - 100 * SAFE_DIVIDE(gp0_2025, budget_sales_2025), 2) AS gm0_yoy_change_pct_points
FROM pivoted
WHERE dns_2025 >= 100000
  AND dns_2026 >= 100000
  AND budget_sales_2025 > 0
  AND budget_sales_2026 > 0
ORDER BY gp0_yoy_change_k DESC
LIMIT 10;
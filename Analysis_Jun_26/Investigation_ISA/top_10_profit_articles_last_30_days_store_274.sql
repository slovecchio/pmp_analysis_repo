-- ################
-- Initial Question:
-- "What are my top 10 most profitable articles the last 7-days, 30-days and fiscal YTD?"
-- ################
-- Revised Question:
-- What are the top 10 most profitable articles in US stores for the 7-day window ending 2026-05-31, 30-day window ending 2026-05-31, and full May 2026?
-- ################
-- Answer:
-- Query returned top 10 articles for each period.
-- Query run date: 2026-07-17.
--
-- period       | item_no  | gp0_k | dns_k  | budget_sales_k | gm0_pct
-- last_30_days | 80275887 | 42467 | 138654 | 141362         | 30.04
-- last_30_days | 20275885 | 34606 | 105642 | 107963         | 32.05
-- last_30_days | 00473546 | 32912 | 75444  | 76258          | 43.16
-- last_30_days | 00160215 | 23417 | 44475  | 45259          | 51.74
-- last_30_days | 40300662 | 21716 | 45256  | 46085          | 47.12
-- last_30_days | 60473548 | 18863 | 38393  | 38741          | 48.69
-- last_30_days | 20323805 | 18757 | 43596  | 42188          | 44.46
-- last_30_days | 10069763 | 15763 | 50783  | 39368          | 40.04
-- last_30_days | 90249483 | 15460 | 30146  | 30642          | 50.45
-- last_30_days | 20275814 | 14537 | 60857  | 63434          | 22.92
-- last_7_days  | 80275887 | 10372 | 33573  | 34527          | 30.04
-- last_7_days  | 00473546 | 8074  | 18453  | 18708          | 43.16
-- last_7_days  | 20275885 | 7639  | 23175  | 23831          | 32.05
-- last_7_days  | 00160215 | 6257  | 11851  | 12093          | 51.74
-- last_7_days  | 20323805 | 4938  | 11460  | 11107          | 44.46
-- last_7_days  | 40300662 | 4933  | 10294  | 10469          | 47.12
-- last_7_days  | 60473548 | 4585  | 9317   | 9417           | 48.69
-- last_7_days  | 10069763 | 4218  | 13645  | 10534          | 40.04
-- last_7_days  | 90249483 | 3921  | 7615   | 7771           | 50.45
-- last_7_days  | 20275814 | 3703  | 15320  | 16159          | 22.92
-- may_2026     | 80275887 | 43879 | 143325 | 146064         | 30.04
-- may_2026     | 20275885 | 35574 | 108622 | 110982         | 32.05
-- may_2026     | 00473546 | 33776 | 77456  | 78262          | 43.16
-- may_2026     | 00160215 | 24197 | 45976  | 46766          | 51.74
-- may_2026     | 40300662 | 22229 | 46375  | 47174          | 47.12
-- may_2026     | 60473548 | 19418 | 39533  | 39881          | 48.69
-- may_2026     | 20323805 | 19385 | 45096  | 43600          | 44.46
-- may_2026     | 10069763 | 16347 | 52716  | 40827          | 40.04
-- may_2026     | 90249483 | 15949 | 31112  | 31611          | 50.45
-- may_2026     | 20275814 | 15024 | 62980  | 65561          | 22.92
-- ################
-- Assumptions/Doubts:
-- - Retail Unit US is used.
-- - The broad period starts on 2026-05-01 and ends on 2026-05-31.
-- - The 7-day period is 2026-05-25 to 2026-05-31.
-- - The 30-day period is 2026-05-02 to 2026-05-31.
-- - Profitability is ranked by GP0 amount.
-- - Dashboard row-view logic is used for GM0 %: GP0 / Sales Budgeted Price.
-- - Source is the derived profitability table, which is already extracted from the consolidated GP goods view and includes item-level info.
-- ################
-- Check with the dashboard:
-- (put here if the number were checked in the main dashboard - to be filled manually)
-- ################
-- Scope:
-- - Retail Unit: US
-- - Windows: 2026-05-25 to 2026-05-31, 2026-05-02 to 2026-05-31, and 2026-05-01 to 2026-05-31
-- - Source table/view: `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
-- - Runner/Billing project: ingka-sot-isa-dev
-- - Dry-run cost (observed on derived source): 13,361,615,064 bytes (~13.36 GB)
--
-- Cost check command:
-- bq query --project_id=ingka-sot-isa-dev --use_legacy_sql=false --dry_run "$(sed -n '/^WITH /,$p' top_10_most_profitable_articles_7d_30d_ytd_store_274.sql)"

WITH item_metrics AS (
  SELECT
    item_no,
    SUM(IF(transaction_date BETWEEN DATE '2026-05-25' AND DATE '2026-05-31', gross_profit_gp0_amount, 0)) AS gp0_7d,
    SUM(IF(transaction_date BETWEEN DATE '2026-05-25' AND DATE '2026-05-31', total_delivered_sales_net_amount, 0)) AS dns_7d,
    SUM(IF(transaction_date BETWEEN DATE '2026-05-25' AND DATE '2026-05-31', total_bud_sales_amount, 0)) AS budget_sales_7d,
    SUM(IF(transaction_date BETWEEN DATE '2026-05-02' AND DATE '2026-05-31', gross_profit_gp0_amount, 0)) AS gp0_30d,
    SUM(IF(transaction_date BETWEEN DATE '2026-05-02' AND DATE '2026-05-31', total_delivered_sales_net_amount, 0)) AS dns_30d,
    SUM(IF(transaction_date BETWEEN DATE '2026-05-02' AND DATE '2026-05-31', total_bud_sales_amount, 0)) AS budget_sales_30d,
    SUM(gross_profit_gp0_amount) AS gp0_ytd,
    SUM(total_delivered_sales_net_amount) AS dns_ytd,
    SUM(total_bud_sales_amount) AS budget_sales_ytd
  FROM `ingka-sot-isa-dev.isa_derived.derived_daily_profitability`
  WHERE retail_unit_code = 'US'
    AND item_no IS NOT NULL
    AND transaction_date BETWEEN DATE '2026-05-01' AND DATE '2026-05-31'
  GROUP BY item_no
),
ranked AS (
  SELECT 'last_7_days' AS period, item_no, gp0_7d AS gp0, dns_7d AS dns, budget_sales_7d AS budget_sales FROM item_metrics
  UNION ALL
  SELECT 'last_30_days' AS period, item_no, gp0_30d AS gp0, dns_30d AS dns, budget_sales_30d AS budget_sales FROM item_metrics
  UNION ALL
  SELECT 'may_2026' AS period, item_no, gp0_ytd AS gp0, dns_ytd AS dns, budget_sales_ytd AS budget_sales FROM item_metrics
)
SELECT
  period,
  item_no,
  ROUND(gp0 / 1000, 0) AS gp0_k,
  ROUND(dns / 1000, 0) AS dns_k,
  ROUND(budget_sales / 1000, 0) AS budget_sales_k,
  ROUND(100 * SAFE_DIVIDE(gp0, budget_sales), 2) AS gm0_pct
FROM ranked
WHERE gp0 > 0
  AND budget_sales > 0
QUALIFY ROW_NUMBER() OVER (PARTITION BY period ORDER BY gp0 DESC) <= 10
ORDER BY period, gp0_k DESC;

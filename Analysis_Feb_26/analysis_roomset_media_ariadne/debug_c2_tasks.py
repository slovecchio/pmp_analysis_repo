"""Find all C2 tasks to understand the 6-task burst."""
from google.cloud import bigquery

client = bigquery.Client(project="ingka-sot-cfm-dev")

# All C2 tasks ever
print("=== ALL C2 tasks for store 274 ===")
for r in client.query("""
    SELECT
        DATE(created_local_dt) AS dt,
        task_type,
        reason,
        item_no,
        SUBSTR(item_name, 1, 35) AS item_name_short,
        state,
        item_count
    FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
    WHERE store_no = '274' AND media_name = 'C2'
    ORDER BY created_local_dt
""").result():
    print(f"  {r.dt} | {r.task_type:8s} | {r.reason:25s} | {r.item_no} | {r.item_name_short or '':35s} | {r.state:10s} | cnt={r.item_count}")

# Also check the rolling 14d logic: show daily task counts
print("\n=== C2 daily task counts ===")
for r in client.query("""
    SELECT
        DATE(created_local_dt) AS dt,
        COUNT(*) AS tasks
    FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
    WHERE store_no = '274' AND media_name = 'C2'
    GROUP BY 1
    ORDER BY 1
""").result():
    print(f"  {r.dt}: {r.tasks} tasks")

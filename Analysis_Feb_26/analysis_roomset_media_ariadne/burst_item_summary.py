"""Summarize total item quantity and unique items for each Visual 03 example burst."""
from google.cloud import bigquery

client = bigquery.Client(project="ingka-sot-cfm-dev")

# The 6 examples from Visual 03 with their burst windows (±14 days around change_date)
examples = [
    ("KD03", "2025-12-01", "2025-12-25"),
    ("L11",  "2025-12-29", "2026-01-26"),
    ("B10",  "2025-10-14", "2025-11-11"),
    ("L09",  "2025-12-25", "2026-01-22"),
    ("C2",   "2025-11-03", "2025-12-01"),
    ("L03",  "2026-01-08", "2026-02-05"),
]

print(f"{'Room':<8} {'Tasks':>5} {'Total Qty':>10} {'Unique Items':>13} {'Reasons'}")
print("-" * 70)

for media_name, start, end in examples:
    q = f"""
        SELECT
            COUNT(*) AS tasks,
            SUM(SAFE_CAST(item_count AS INT64)) AS total_qty,
            COUNT(DISTINCT item_no) AS unique_items,
            STRING_AGG(DISTINCT reason, ', ') AS reasons
        FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
        WHERE store_no = '274'
          AND media_name = '{media_name}'
          AND DATE(created_local_dt) BETWEEN '{start}' AND '{end}'
    """
    for r in client.query(q).result():
        print(f"{media_name:<8} {r.tasks:>5} {r.total_qty or 0:>10} {r.unique_items:>13} {r.reasons}")

# Also show per-day detail for each example
print("\n" + "=" * 90)
print("Per-day detail for each example")
print("=" * 90)

for media_name, start, end in examples:
    q = f"""
        SELECT
            DATE(created_local_dt) AS dt,
            COUNT(*) AS tasks,
            SUM(SAFE_CAST(item_count AS INT64)) AS total_qty,
            COUNT(DISTINCT item_no) AS unique_items,
            STRING_AGG(DISTINCT reason, ', ') AS reasons
        FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
        WHERE store_no = '274'
          AND media_name = '{media_name}'
          AND DATE(created_local_dt) BETWEEN '{start}' AND '{end}'
        GROUP BY 1
        ORDER BY 1
    """
    rows = list(client.query(q).result())
    if rows:
        print(f"\n--- {media_name} ---")
        for r in rows:
            print(f"  {r.dt}  tasks={r.tasks:>3}  qty={r.total_qty or 0:>3}  unique_items={r.unique_items:>3}  {r.reasons}")
    else:
        print(f"\n--- {media_name} --- (no tasks in window)")

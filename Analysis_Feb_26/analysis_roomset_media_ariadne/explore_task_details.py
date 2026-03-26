"""Explore FIXA media_task metadata: task types, reasons, states, item details."""
from google.cloud import bigquery

client = bigquery.Client(project="ingka-sot-cfm-dev")

# 1) distinct states
print("=== distinct state ===")
for r in client.query("""
    SELECT DISTINCT state
    FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
    WHERE store_no = '274'
    ORDER BY 1
""").result():
    print(f"  {r.state}")

# 2) top reasons
print("\n=== top reasons ===")
for r in client.query("""
    SELECT reason, COUNT(*) cnt
    FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
    WHERE store_no = '274'
    GROUP BY 1 ORDER BY cnt DESC LIMIT 20
""").result():
    print(f"  {str(r.reason):45s} {r.cnt}")

# 3) item_type breakdown
print("\n=== item_type ===")
for r in client.query("""
    SELECT item_type, COUNT(*) cnt
    FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
    WHERE store_no = '274'
    GROUP BY 1 ORDER BY cnt DESC LIMIT 10
""").result():
    print(f"  {str(r.item_type):30s} {r.cnt}")

# 4) task_type breakdown
print("\n=== task_type ===")
for r in client.query("""
    SELECT task_type, COUNT(*) cnt
    FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
    WHERE store_no = '274'
    GROUP BY 1 ORDER BY cnt DESC
""").result():
    print(f"  {r.task_type:20s} {r.cnt}")

# 5) KD03 tasks in Dec 2025 (our biggest burst)
print("\n=== KD03 tasks Dec 2025 (burst) ===")
for r in client.query("""
    SELECT
        DATE(created_local_dt) AS dt,
        task_type,
        reason,
        item_no,
        SUBSTR(item_name, 1, 30) AS item_name_short,
        SUBSTR(description, 1, 50) AS desc_short,
        state,
        item_count
    FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
    WHERE store_no = '274' AND media_name = 'KD03'
      AND DATE(created_local_dt) BETWEEN '2025-12-01' AND '2025-12-31'
    ORDER BY created_local_dt
""").result():
    print(f"  {r.dt} | {r.task_type:8s} | {str(r.reason):25s} | {r.item_no} | {r.item_name_short or '':30s} | {r.desc_short or '':50s} | {r.state:10s} | cnt={r.item_count}")

# 6) C2 tasks in Nov 2025 (positive burst)
print("\n=== C2 tasks Nov 2025 (positive burst) ===")
for r in client.query("""
    SELECT
        DATE(created_local_dt) AS dt,
        task_type,
        reason,
        item_no,
        SUBSTR(item_name, 1, 30) AS item_name_short,
        SUBSTR(description, 1, 50) AS desc_short,
        state,
        item_count
    FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
    WHERE store_no = '274' AND media_name = 'C2'
      AND DATE(created_local_dt) BETWEEN '2025-11-01' AND '2025-11-30'
    ORDER BY created_local_dt
""").result():
    print(f"  {r.dt} | {r.task_type:8s} | {str(r.reason):25s} | {r.item_no} | {r.item_name_short or '':30s} | {r.desc_short or '':50s} | {r.state:10s} | cnt={r.item_count}")

# 7) B10 tasks in Oct 2025 (another burst)
print("\n=== B10 tasks Oct 2025 (burst) ===")
for r in client.query("""
    SELECT
        DATE(created_local_dt) AS dt,
        task_type,
        reason,
        item_no,
        SUBSTR(item_name, 1, 30) AS item_name_short,
        SUBSTR(description, 1, 50) AS desc_short,
        state,
        item_count
    FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
    WHERE store_no = '274' AND media_name = 'B10'
      AND DATE(created_local_dt) BETWEEN '2025-10-15' AND '2025-11-15'
    ORDER BY created_local_dt
""").result():
    print(f"  {r.dt} | {r.task_type:8s} | {str(r.reason):25s} | {r.item_no} | {r.item_name_short or '':30s} | {r.desc_short or '':50s} | {r.state:10s} | cnt={r.item_count}")

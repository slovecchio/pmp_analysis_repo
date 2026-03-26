"""Debug: find what standardize_location maps to 'C2' and which FIXA names overlap."""
import sys
sys.path.insert(0, "/Users/salvatore.lovecchio/Library/CloudStorage/OneDrive-IKEA/Escritorio/pmp_analysis_repo/Analysis_Feb_26/analysis_roomset_media_ariadne")

from analysis_common import standardize_location
from google.cloud import bigquery

# 1) What does standardize_location produce for C-prefix?
test_names = ["C2", "C02", "C 2", "C 02", "C2 ", " C2"]
for n in test_names:
    print(f"  standardize_location('{n}') => '{standardize_location(n)}'")

# 2) All C-prefix media names in FIXA for store 274
client = bigquery.Client(project="ingka-sot-cfm-dev")
print("\n=== All C-prefix media_names in FIXA media_task ===")
for r in client.query("""
    SELECT media_name, COUNT(*) AS cnt
    FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
    WHERE store_no = '274' AND UPPER(media_name) LIKE 'C%'
    GROUP BY 1 ORDER BY 1
""").result():
    std = standardize_location(r.media_name)
    print(f"  '{r.media_name}' => std='{std}'  tasks={r.cnt}")

# 3) Also check media_item for C-prefix
print("\n=== All C-prefix media_names in FIXA media_item ===")
for r in client.query("""
    SELECT media_name, COUNT(*) AS cnt
    FROM `ingka-pmp-fixa-prod.report_fixa.media_item`
    WHERE store_no = '274' AND UPPER(media_name) LIKE 'C%'
    GROUP BY 1 ORDER BY 1
""").result():
    std = standardize_location(r.media_name)
    print(f"  '{r.media_name}' => std='{std}'  items={r.cnt}")

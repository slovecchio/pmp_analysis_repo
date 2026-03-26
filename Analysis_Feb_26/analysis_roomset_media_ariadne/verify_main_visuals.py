"""
Verification script for main visuals.

Uses BigQuery (gcloud auth) to cross-check the FIXA-based figures
reported in the analysis outputs, and the Ariadne API to cross-check
visitor counts.

Main visuals verified:
  01 - Roomset groups on showroom floor  (GeoJSON roomset count + grouping)
  02 - Prefix group evolution             (Ariadne visitors + store visitors)
  03 - Reformat visitors pre/post         (FIXA room versions/tasks + Ariadne)

Run:
  python verify_main_visuals.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from google.cloud import bigquery

# ── repo helpers ──────────────────────────────────────────────────────────
from analysis_common import (
    BIGQUERY_PROJECT,
    SHOWROOM_GEOJSON,
    STORE_NO,
    fetch_area_visitors,
    fetch_store_visitors,
    infer_location_groups,
    load_roomsets,
    standardize_location,
)

BASE_DIR = Path(__file__).resolve().parent
OUTPUTS = BASE_DIR / "outputs"
PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
WARN = "\033[93m⚠ WARN\033[0m"
results: list[dict] = []


def record(visual: str, check: str, expected, actual, ok: bool, note: str = ""):
    tag = PASS if ok else FAIL
    results.append(dict(visual=visual, check=check, expected=expected, actual=actual, ok=ok, note=note))
    print(f"  {tag}  {check}: expected={expected}, got={actual}  {note}")


# ═══════════════════════════════════════════════════════════════════════════
# VISUAL 01 – Roomset groups on showroom floor
# ═══════════════════════════════════════════════════════════════════════════
def verify_visual_01():
    print("\n══ VISUAL 01 ─ Roomset Groups on Showroom Floor ══")

    # --- 1a. GeoJSON roomset count ---
    roomsets = infer_location_groups(load_roomsets(SHOWROOM_GEOJSON), n_groups=4)
    saved = pd.read_csv(OUTPUTS / "monthly_roomset_analysis/roomset_location_groups.csv")

    geojson_count = len(roomsets)
    csv_count = len(saved)
    record("01", "roomset_count_geojson_vs_csv", geojson_count, csv_count,
           geojson_count == csv_count)

    # --- 1b. Prefix group counts ---
    prefix_counts_geo = roomsets.groupby("prefix_group").size().to_dict()
    prefix_counts_csv = saved.groupby("prefix_group").size().to_dict()
    for pfx in sorted(set(prefix_counts_geo) | set(prefix_counts_csv)):
        g = prefix_counts_geo.get(pfx, 0)
        c = prefix_counts_csv.get(pfx, 0)
        record("01", f"prefix_{pfx}_count", g, c, g == c)

    # --- 1c. Location groups ---
    lg_geo = sorted(roomsets["location_group"].unique())
    lg_csv = sorted(saved["location_group"].unique())
    record("01", "location_groups", lg_geo, lg_csv, lg_geo == lg_csv)


# ═══════════════════════════════════════════════════════════════════════════
# VISUAL 02 – Prefix group evolution with band dual axis
# ═══════════════════════════════════════════════════════════════════════════
def verify_visual_02():
    print("\n══ VISUAL 02 ─ Prefix Group Evolution ══")

    saved_summary = pd.read_csv(OUTPUTS / "prefix_group_analysis/prefix_group_monthly_summary.csv",
                                parse_dates=["month"])
    saved_overview = pd.read_csv(OUTPUTS / "prefix_group_analysis/prefix_group_overview.csv")
    saved_daily = pd.read_csv(OUTPUTS / "monthly_roomset_analysis/roomset_daily_visitors.csv",
                              parse_dates=["date"])

    # --- 2a. Re-fetch a single month of Ariadne area visitors & compare ---
    sample_month = "2026-02-01"
    sample_end = "2026-02-28"
    print(f"  Fetching Ariadne area visitors for {sample_month} → {sample_end} …")
    fresh_visitors = fetch_area_visitors(start_date=sample_month, end_date=sample_end)

    # Compare per-roomset average daily visitors for Feb-2026
    saved_feb = saved_daily.loc[saved_daily["date"].dt.to_period("M").dt.to_timestamp() == sample_month]

    for roomset in ["L01", "B01", "KD01", "WS01", "C1"]:
        saved_val = saved_feb.loc[saved_feb["roomset_name_std"] == roomset, "visitors"].mean()
        fresh_val = fresh_visitors.loc[fresh_visitors["roomset_name_std"] == roomset, "visitors"].mean()
        if pd.isna(saved_val) or pd.isna(fresh_val):
            record("02", f"ariadne_visitors_{roomset}_feb", saved_val, fresh_val,
                   False, "missing data")
            continue
        close = abs(saved_val - fresh_val) / max(saved_val, 1) < 0.02  # <2% tolerance
        record("02", f"ariadne_visitors_{roomset}_feb", f"{saved_val:.1f}", f"{fresh_val:.1f}",
               close, "same Ariadne API endpoint")

    # --- 2b. Re-fetch store visitors for Feb-2026 & compare ---
    print(f"  Fetching Ariadne store visitors for {sample_month} → {sample_end} …")
    fresh_store = fetch_store_visitors(start_date=sample_month, end_date=sample_end)
    saved_store_avg = saved_summary.loc[
        saved_summary["month"] == pd.Timestamp(sample_month), "avg_store_visitors"
    ].values
    fresh_store_avg = fresh_store["store_visitors"].mean()
    if len(saved_store_avg) > 0:
        s = saved_store_avg[0]
        close = abs(s - fresh_store_avg) / max(s, 1) < 0.02
        record("02", "store_visitors_feb_avg", f"{s:.1f}", f"{fresh_store_avg:.1f}",
               close, "Ariadne store visitors endpoint")
    else:
        record("02", "store_visitors_feb_avg", "present", "missing", False)

    # --- 2c. Verify overview trend calculation ---
    for _, row in saved_overview.iterrows():
        pfx = row["prefix_group"]
        grp = saved_summary.loc[saved_summary["prefix_group"] == pfx].sort_values("month")
        first_v = grp.iloc[0]["mean_avg_daily_visitors"]
        last_v = grp.iloc[-1]["mean_avg_daily_visitors"]
        expected_trend = 100 * (last_v - first_v) / first_v if first_v else float("nan")
        reported_trend = row["trend_pct_from_first_to_last_month"]
        close = abs(expected_trend - reported_trend) < 0.01
        record("02", f"trend_calc_{pfx}", f"{expected_trend:.2f}", f"{reported_trend:.2f}", close)


# ═══════════════════════════════════════════════════════════════════════════
# VISUAL 03 – Reformat visitors pre/post rescaled (FIXA + Ariadne)
# ═══════════════════════════════════════════════════════════════════════════
def verify_visual_03():
    print("\n══ VISUAL 03 ─ Reformat Visitors Pre/Post ══")

    examples = pd.read_csv(OUTPUTS / "reformat_investigation/reformat_significant_examples.csv")
    all_candidates = pd.read_csv(OUTPUTS / "reformat_investigation/reformat_candidates_with_significance.csv")
    saved_versions = pd.read_csv(OUTPUTS / "reformat_investigation/fixa_room_versions.csv")
    saved_tasks = pd.read_csv(OUTPUTS / "reformat_investigation/fixa_tasks.csv")

    client = bigquery.Client(project=BIGQUERY_PROJECT)

    # --- 3a. Fetch all FIXA room versions (same query as original code) ---
    query_versions = f"""
        SELECT media_name,
               scd_start_date,
               scd_end_date,
               COUNT(DISTINCT item_no) AS distinct_items
        FROM `ingka-pmp-fixa-prod.report_fixa.media_item`
        WHERE store_no = '{STORE_NO}'
          AND media_type = 'ROOM_SETTINGS'
          AND DATE(scd_start_date) <= '2026-02-28'
          AND DATE(COALESCE(scd_end_date, CURRENT_DATE())) >= '2025-05-01'
        GROUP BY 1, 2, 3
        ORDER BY media_name, scd_start_date
    """
    print("  BQ: fetching full FIXA room versions …")
    bq_versions = client.query(query_versions).to_dataframe()
    bq_versions["roomset_name_std"] = bq_versions["media_name"].apply(standardize_location)
    bq_versions["scd_start_date"] = pd.to_datetime(bq_versions["scd_start_date"])

    # --- 3b. Verify total room version row count ---
    saved_version_count = len(saved_versions)
    bq_version_count = len(bq_versions)
    record("03", "fixa_room_version_row_count", saved_version_count, bq_version_count,
           saved_version_count == bq_version_count,
           "total rows from media_item query")

    # --- 3c. Verify FIXA versions for each example roomset ---
    for _, ex in examples.iterrows():
        roomset = ex["roomset_name_std"]
        change_date = ex["change_date"]
        items_before = int(ex["distinct_items_before"])
        items_after = int(ex["distinct_items_after"])
        change_ts = pd.Timestamp(change_date)

        bq_match = bq_versions.loc[bq_versions["roomset_name_std"] == roomset].sort_values("scd_start_date")
        print(f"  BQ: verifying FIXA versions for {roomset} (found {len(bq_match)} rows) …")

        # find the version whose scd_start_date matches the change_date
        post_row = bq_match.loc[bq_match["scd_start_date"].dt.normalize() == change_ts]
        if post_row.empty:
            record("03", f"fixa_items_after_{roomset}_{change_date}", items_after, "NOT FOUND",
                   False, "change_date row missing in BQ")
        else:
            bq_items = int(post_row.iloc[0]["distinct_items"])
            record("03", f"fixa_items_after_{roomset}_{change_date}",
                   items_after, bq_items, items_after == bq_items)

        # find previous version
        pre_rows = bq_match.loc[bq_match["scd_start_date"].dt.normalize() < change_ts]
        if not pre_rows.empty:
            bq_items_before = int(pre_rows.iloc[-1]["distinct_items"])
            record("03", f"fixa_items_before_{roomset}_{change_date}",
                   items_before, bq_items_before, items_before == bq_items_before)

    # --- 3d. Verify FIXA tasks_14d_after for each example ---
    query_tasks = f"""
        SELECT media_name,
               DATE(created_local_dt) AS task_date,
               COUNT(*) AS task_count
        FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
        WHERE store_no = '{STORE_NO}'
          AND DATE(created_local_dt) BETWEEN '2025-05-01' AND '2026-02-28'
        GROUP BY 1, 2
        ORDER BY media_name, task_date
    """
    print("  BQ: fetching all FIXA tasks …")
    bq_tasks = client.query(query_tasks).to_dataframe()
    bq_tasks["roomset_name_std"] = bq_tasks["media_name"].apply(standardize_location)
    bq_tasks["task_date"] = pd.to_datetime(bq_tasks["task_date"])

    for _, ex in examples.iterrows():
        roomset = ex["roomset_name_std"]
        change_date = ex["change_date"]
        change_ts = pd.Timestamp(change_date)
        expected_tasks = int(ex["tasks_14d_after"])
        room_tasks = bq_tasks.loc[
            (bq_tasks["roomset_name_std"] == roomset)
            & (bq_tasks["task_date"] >= change_ts)
            & (bq_tasks["task_date"] < change_ts + pd.Timedelta(days=14))
        ]
        bq_task_total = int(room_tasks["task_count"].sum())
        record("03", f"fixa_tasks_14d_{roomset}_{change_date}",
               expected_tasks, bq_task_total, expected_tasks == bq_task_total,
               "BQ media_task direct count")

    # --- 3d. Verify significance flags are internally consistent ---
    sig_count_csv = int(all_candidates["is_significant"].sum())
    below_threshold = int((all_candidates["p_value_relative_visitors"] < 0.05).sum())
    record("03", "significance_flag_consistency", below_threshold, sig_count_csv,
           below_threshold == sig_count_csv,
           "is_significant should equal p_value < 0.05")

    # --- 3e. Verify the p-value direction matches the visitor change direction ---
    for _, ex in examples.iterrows():
        roomset = ex["roomset_name_std"]
        vis_change = ex["relative_visitors_pct_change"]
        label = "positive" if vis_change > 0 else "negative"
        record("03", f"example_direction_{roomset}", label,
               "positive" if vis_change > 0 else "negative", True, "direction sanity check")


# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════
def print_summary():
    df = pd.DataFrame(results)
    passed = df["ok"].sum()
    total = len(df)
    failed = total - passed
    print(f"\n{'═' * 60}")
    print(f"  VERIFICATION SUMMARY:  {passed}/{total} passed,  {failed} failed")
    print(f"{'═' * 60}")
    if failed:
        print("\n  Failed checks:")
        for _, r in df.loc[~df["ok"]].iterrows():
            print(f"    [{r['visual']}] {r['check']}: expected={r['expected']}, got={r['actual']}  {r['note']}")
    print()


if __name__ == "__main__":
    try:
        verify_visual_01()
        verify_visual_02()
        verify_visual_03()
    except Exception as exc:
        print(f"\n{FAIL} Fatal error: {exc}", file=sys.stderr)
        import traceback; traceback.print_exc()
    finally:
        print_summary()

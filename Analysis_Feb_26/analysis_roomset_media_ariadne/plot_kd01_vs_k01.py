"""Preview: KD01 Ariadne visitor trend overlaid with K01 FIXA tasks."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from google.cloud import bigquery
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from analysis_common import fetch_area_visitors, fetch_store_visitors

START, END = "2025-05-01", "2026-02-28"

# --- Ariadne visitors for KD01 (= KD1 in Ariadne) ---
visitors = fetch_area_visitors(start_date=START, end_date=END)
store = fetch_store_visitors(start_date=START, end_date=END)
kd01_vis = visitors.loc[visitors["roomset_name_std"] == "KD01"].merge(store, on="date", how="left")
kd01_vis["rel_pct"] = 100.0 * kd01_vis["visitors"].values / kd01_vis["store_visitors"].replace(0, float("nan")).values
kd01_vis = kd01_vis.sort_values("date").copy()
kd01_vis["rel_7d"] = kd01_vis["rel_pct"].rolling(7, min_periods=1).mean()

# --- FIXA tasks for K01 (not KD01) ---
client = bigquery.Client(project="ingka-sot-cfm-dev")
q = f"""
SELECT
  DATE(created_local_dt) AS task_date,
  COUNT(*) AS task_count
FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
WHERE store_no = '274'
  AND media_name = 'K01'
  AND DATE(created_local_dt) BETWEEN DATE('{START}') AND DATE('{END}')
GROUP BY 1 ORDER BY 1
"""
k01_tasks = client.query(q).to_dataframe()
k01_tasks["task_date"] = pd.to_datetime(k01_tasks["task_date"])

print(f"KD01 visitor days: {len(kd01_vis)}")
print(f"K01 task daily rows: {len(k01_tasks)}, total tasks: {k01_tasks['task_count'].sum()}")

# --- Plot ---
plot_min = kd01_vis["date"].min() - pd.Timedelta(days=7)
plot_max = kd01_vis["date"].max() + pd.Timedelta(days=7)

fig, ax = plt.subplots(figsize=(14, 5))

# Left: visitor line
ax.plot(kd01_vis["date"], kd01_vis["rel_7d"], color="#4C78A8", linewidth=2.4, label="KD01 visitors (7d avg)")
ax.set_ylabel("KD01 visitors / store visitors (%)", fontsize=9)

# Right: K01 weekly task bars
all_weeks = pd.date_range(
    plot_min - pd.Timedelta(days=plot_min.weekday()), plot_max, freq="W-MON"
)
if not k01_tasks.empty:
    rt = k01_tasks.copy()
    rt["week_start"] = rt["task_date"].dt.to_period("W-SUN").dt.start_time
    wt = rt.groupby("week_start", as_index=False)["task_count"].sum()
else:
    wt = pd.DataFrame(columns=["week_start", "task_count"])
wt = wt.set_index("week_start").reindex(all_weeks, fill_value=0).rename_axis("week_start").reset_index()

ax_r = ax.twinx()
ax_r.bar(wt["week_start"], wt["task_count"], width=6.0, color="#FF6B6B", alpha=0.35, zorder=1)
ax_r.set_ylabel("K01 tasks / week", fontsize=9, color="#CC3333")
ax_r.tick_params(axis="y", labelcolor="#CC3333")
ax_r.set_ylim(bottom=0)
ax.set_zorder(ax_r.get_zorder() + 1)
ax.patch.set_visible(False)

ax.set_title(
    "KD01 (Ariadne visitors) vs K01 (FIXA tasks) — are they the same room?",
    fontsize=12, fontweight="bold",
)
ax.grid(alpha=0.2)

task_patch = Patch(facecolor="#FF6B6B", alpha=0.35, label="K01 weekly tasks (FIXA)")
handles, labels = ax.get_legend_handles_labels()
handles.append(task_patch)
labels.append("K01 weekly tasks (FIXA)")
ax.legend(handles=handles, labels=labels, loc="upper left", fontsize=8)

fig.tight_layout()
out_dir = Path(__file__).parent / "outputs" / "reformat_investigation"
out_dir.mkdir(parents=True, exist_ok=True)
out = out_dir / "KD01_visitors_vs_K01_tasks_preview.png"
fig.savefig(out, dpi=240, bbox_inches="tight")
plt.close(fig)
print(f"Saved: {out}")

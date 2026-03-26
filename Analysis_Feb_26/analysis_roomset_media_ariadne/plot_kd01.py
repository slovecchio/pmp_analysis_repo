"""One-off Visual 03-style chart for KD01."""
import sys, pandas as pd, numpy as np
sys.path.insert(0, ".")
from detect_room_reformat_impact import (
    fetch_fixa_tasks, build_relative_visitor_table, infer_reformat_candidates,
    WINDOW_DAYS,
)
from google.cloud import bigquery
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

client = bigquery.Client(project="ingka-sot-cfm-dev")
tasks = fetch_fixa_tasks(client, "2025-05-01", "2026-02-28")
rel = build_relative_visitor_table("2025-05-01", "2026-02-28")

room = "KD01"
room_tasks = tasks.loc[tasks["roomset_name_std"] == room].sort_values("task_date")
room_vis = rel.loc[rel["roomset_name_std"] == room].sort_values("date").copy()

print(f"KD01 tasks: {len(room_tasks)} daily rows, total tasks = {room_tasks['task_count'].sum()}")
print(f"KD01 visitor days: {len(room_vis)}")

# detect bursts
all_cands = infer_reformat_candidates(tasks)
kd01_bursts = all_cands.loc[all_cands["roomset_name_std"] == room]
print(f"Bursts detected: {len(kd01_bursts)}")
if not kd01_bursts.empty:
    print(kd01_bursts[["change_date", "peak_date", "tasks_14d", "spike_ratio"]].to_string(index=False))

# plot range
plot_min = room_vis["date"].min() - pd.Timedelta(days=7)
plot_max = room_vis["date"].max() + pd.Timedelta(days=7)
room_vis["rel_7d"] = room_vis["relative_visitors_pct"].rolling(7, min_periods=1).mean()

fig, ax = plt.subplots(figsize=(13, 4.5))

# visitor line (left)
ax.plot(room_vis["date"], room_vis["rel_7d"], color="#4C78A8", linewidth=2.4, label="7-day avg ratio")

# burst red lines
for _, b in kd01_bursts.iterrows():
    bd = pd.to_datetime(b["change_date"])
    ax.axvline(bd, color="#FF6B6B", linewidth=1.8, alpha=0.9)

# weekly tasks (right)
all_weeks = pd.date_range(
    plot_min - pd.Timedelta(days=plot_min.weekday()),
    plot_max,
    freq="W-MON",
)
if not room_tasks.empty:
    rt = room_tasks.copy()
    rt["week_start"] = rt["task_date"].dt.to_period("W-SUN").dt.start_time
    wt = rt.groupby("week_start", as_index=False)["task_count"].sum()
else:
    wt = pd.DataFrame(columns=["week_start", "task_count"])
wt = (
    wt.set_index("week_start")
    .reindex(all_weeks, fill_value=0)
    .rename_axis("week_start")
    .reset_index()
)

ax_r = ax.twinx()
ax_r.bar(wt["week_start"], wt["task_count"], width=6.0, color="#FF6B6B", alpha=0.35, zorder=1)
ax_r.set_ylabel("Tasks / week", fontsize=9, color="#CC3333")
ax_r.tick_params(axis="y", labelcolor="#CC3333")
ax_r.set_ylim(bottom=0)
ax.set_zorder(ax_r.get_zorder() + 1)
ax.patch.set_visible(False)

ax.set_ylabel("Visitors / store visitors (%)", fontsize=9)
ax.set_title("KD01 — FIXA task bursts vs relative visitor flow", fontsize=12, fontweight="bold")
ax.grid(alpha=0.2)

task_patch = Patch(facecolor="#FF6B6B", alpha=0.35, label="Weekly tasks")
handles, labels = ax.get_legend_handles_labels()
handles.append(task_patch)
labels.append("Weekly tasks")
ax.legend(handles=handles, labels=labels, loc="upper left", fontsize=8)

fig.tight_layout()
from pathlib import Path
out_dir = Path(__file__).parent / "outputs" / "reformat_investigation"
out_dir.mkdir(parents=True, exist_ok=True)
out = out_dir / "KD01_reformat_visual03.png"
fig.savefig(out, dpi=240, bbox_inches="tight")
plt.close(fig)
print(f"Saved: {out}")

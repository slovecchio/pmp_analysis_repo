from __future__ import annotations

import argparse
from pathlib import Path
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from google.cloud import bigquery

from analysis_common import (
    BASE_DIR,
    BIGQUERY_PROJECT,
    MAIN_VISUALS_DIR,
    STORE_NO,
    fetch_area_durations,
    fetch_area_visitors,
    fetch_store_visitors,
    permutation_p_value,
    safe_pct_change,
    standardize_location,
)

DEFAULT_START_DATE = "2025-08-25"
DEFAULT_END_DATE = "2026-02-28"
OUTPUT_DIR = BASE_DIR / "outputs/reformat_investigation"
MIN_TASKS_14D = 5          # minimum tasks in a 14-day window to flag a reformat
PREFERRED_WINDOW_DAYS = 14 # prefer 2 full weeks for pre/post
FALLBACK_WINDOW_DAYS = 7   # fallback to 1 full week if 2 weeks not available
MIN_WINDOW_OBS = 7         # require at least 1 full week of actual data points
PERMUTATIONS = 3000
SIGNIFICANCE_LEVEL = 0.05
MIN_TASKS_FOR_EXAMPLE = 10  # min tasks_14d to qualify as a "huge burst" example
MIN_ABS_VISITOR_CHG = 10   # min |visitor_change_%| needed for "clear impact"
MAX_EXAMPLES = 2           # how many panels to show (1 positive + 1 negative for slide)
MIN_BURST_DATE = "2025-08-25"  # only consider bursts from end of August 2025 onwards
MIN_PRE_POST_DAYS = 7      # burst must have ≥ 7 days of room before/after data edges


def fetch_fixa_room_versions(client: bigquery.Client, start_date: str, end_date: str) -> pd.DataFrame:
    query = f"""
        SELECT
          media_name,
          scd_start_date,
          scd_end_date,
          COUNT(DISTINCT item_no) AS distinct_items
        FROM `ingka-pmp-fixa-prod.report_fixa.media_item`
        WHERE store_no = '{STORE_NO}'
          AND media_type = 'ROOM_SETTINGS'
          AND DATE(scd_start_date) <= DATE('{end_date}')
          AND DATE(COALESCE(scd_end_date, CURRENT_DATE())) >= DATE('{start_date}')
        GROUP BY 1, 2, 3
        ORDER BY media_name, scd_start_date
    """
    room_versions = client.query(query).to_dataframe()
    room_versions["roomset_name_std"] = room_versions["media_name"].apply(standardize_location)
    room_versions["scd_start_date"] = pd.to_datetime(room_versions["scd_start_date"], errors="coerce")
    room_versions["scd_end_date"] = pd.to_datetime(room_versions["scd_end_date"], errors="coerce")
    return room_versions.dropna(subset=["roomset_name_std", "scd_start_date"]).copy()


def fetch_fixa_tasks(client: bigquery.Client, start_date: str, end_date: str) -> pd.DataFrame:
    query = f"""
        SELECT
          media_name,
          DATE(created_local_dt) AS task_date,
          COUNT(*) AS task_count
        FROM `ingka-pmp-fixa-prod.report_fixa.media_task`
        WHERE store_no = '{STORE_NO}'
          AND DATE(created_local_dt) BETWEEN DATE('{start_date}') AND DATE('{end_date}')
        GROUP BY 1, 2
        ORDER BY media_name, task_date
    """
    tasks = client.query(query).to_dataframe()
    tasks["roomset_name_std"] = tasks["media_name"].apply(standardize_location)
    tasks["task_date"] = pd.to_datetime(tasks["task_date"], errors="coerce")
    return tasks.dropna(subset=["roomset_name_std", "task_date"]).copy()


def infer_reformat_candidates(tasks: pd.DataFrame) -> pd.DataFrame:
    """Detect reformat events purely from FIXA task bursts.

    For each roomset, compute a 14-day rolling task count.
    When the rolling count reaches ≥ MIN_TASKS_14D, the *first* day
    of that burst is flagged as the change_date (red line).
    """
    candidates: list[dict] = []

    for roomset_name, room_tasks in tasks.groupby("roomset_name_std"):
        room_tasks = room_tasks.sort_values("task_date").copy()

        # build a continuous daily index and fill missing days with 0
        date_range = pd.date_range(
            room_tasks["task_date"].min(),
            room_tasks["task_date"].max(),
            freq="D",
        )
        daily = (
            room_tasks.groupby("task_date")["task_count"].sum()
            .reindex(date_range, fill_value=0)
            .rename_axis("task_date")
            .reset_index(name="daily_tasks")
        )
        daily["tasks_14d_rolling"] = daily["daily_tasks"].rolling(14, min_periods=1).sum()

        # compute baseline (median of 14-day rolling) for spike detection
        median_14d = float(daily["tasks_14d_rolling"].median())

        # find contiguous bursts above threshold
        daily["above"] = daily["tasks_14d_rolling"] >= MIN_TASKS_14D
        if not daily["above"].any():
            continue

        # group consecutive above-threshold days into bursts
        daily["burst_id"] = (~daily["above"]).cumsum()
        for _, burst in daily.loc[daily["above"]].groupby("burst_id"):
            change_date = burst["task_date"].iloc[0]  # first day of the burst
            peak_date = burst.loc[burst["tasks_14d_rolling"].idxmax(), "task_date"]
            tasks_14d = int(burst["tasks_14d_rolling"].max())
            total_tasks_burst = int(burst["daily_tasks"].sum())
            spike_above_median = tasks_14d - median_14d
            spike_ratio = tasks_14d / median_14d if median_14d > 0 else float(tasks_14d)

            candidates.append(
                {
                    "roomset_name_std": roomset_name,
                    "change_date": pd.Timestamp(change_date).normalize(),
                    "peak_date": pd.Timestamp(peak_date).normalize(),
                    "tasks_14d": tasks_14d,
                    "total_tasks_burst": total_tasks_burst,
                    "burst_days": len(burst),
                    "median_14d": round(median_14d, 1),
                    "spike_above_median": round(spike_above_median, 1),
                    "spike_ratio": round(spike_ratio, 2),
                }
            )

    if not candidates:
        return pd.DataFrame()

    candidate_df = pd.DataFrame(candidates)
    candidate_df = candidate_df.sort_values("spike_ratio", ascending=False)
    return candidate_df.reset_index(drop=True)


def build_relative_visitor_table(start_date: str, end_date: str) -> pd.DataFrame:
    visitors = fetch_area_visitors(start_date=start_date, end_date=end_date)
    durations = fetch_area_durations(start_date=start_date, end_date=end_date)
    store = fetch_store_visitors(start_date=start_date, end_date=end_date)

    relative = visitors.merge(store, on="date", how="left")
    relative = relative.merge(durations[["date", "roomset_name_std", "avg_time"]], on=["date", "roomset_name_std"], how="left")
    relative["relative_visitors_pct"] = 100 * relative["visitors"] / relative["store_visitors"].replace(0, pd.NA)
    return relative.dropna(subset=["date", "roomset_name_std", "relative_visitors_pct"]).copy()


def evaluate_candidates(candidates: pd.DataFrame, relative_visitors: pd.DataFrame) -> pd.DataFrame:
    evaluated_rows: list[dict] = []

    for _, candidate in candidates.iterrows():
        roomset_name = candidate["roomset_name_std"]
        change_date = pd.to_datetime(candidate["change_date"])
        burst_days = int(candidate["burst_days"])
        room_df = relative_visitors.loc[relative_visitors["roomset_name_std"] == roomset_name].copy()
        if room_df.empty:
            continue

        # dynamic window: at least burst_days, prefer 14d, fallback 7d
        window_days = max(burst_days, PREFERRED_WINDOW_DAYS)

        pre_window = room_df.loc[
            (room_df["date"] >= change_date - pd.Timedelta(days=window_days))
            & (room_df["date"] < change_date)
        ].copy()
        post_window = room_df.loc[
            (room_df["date"] > change_date)
            & (room_df["date"] <= change_date + pd.Timedelta(days=window_days))
        ].copy()

        # if preferred window doesn't have enough data, try fallback
        if len(pre_window) < MIN_WINDOW_OBS or len(post_window) < MIN_WINDOW_OBS:
            window_days = max(burst_days, FALLBACK_WINDOW_DAYS)
            pre_window = room_df.loc[
                (room_df["date"] >= change_date - pd.Timedelta(days=window_days))
                & (room_df["date"] < change_date)
            ].copy()
            post_window = room_df.loc[
                (room_df["date"] > change_date)
                & (room_df["date"] <= change_date + pd.Timedelta(days=window_days))
            ].copy()

        if len(pre_window) < MIN_WINDOW_OBS or len(post_window) < MIN_WINDOW_OBS:
            continue

        pre_rel = pre_window["relative_visitors_pct"].to_numpy(dtype=float)
        post_rel = post_window["relative_visitors_pct"].to_numpy(dtype=float)
        pre_vis = pre_window["visitors"].mean()
        post_vis = post_window["visitors"].mean()
        pre_time = pre_window["avg_time"].mean()
        post_time = post_window["avg_time"].mean()
        pre_rel_mean = float(np.nanmean(pre_rel))
        post_rel_mean = float(np.nanmean(post_rel))
        p_value = permutation_p_value(pre_rel, post_rel, n_permutations=PERMUTATIONS)

        evaluated_rows.append(
            {
                **candidate.to_dict(),
                "window_days_used": window_days,
                "pre_days": len(pre_window),
                "post_days": len(post_window),
                "visitors_pre_28d": pre_vis,
                "visitors_post_28d": post_vis,
                "visitors_pct_change": safe_pct_change(pre_vis, post_vis),
                "avg_time_pre_28d": pre_time,
                "avg_time_post_28d": post_time,
                "avg_time_pct_change": safe_pct_change(pre_time, post_time),
                "relative_visitors_pct_pre_28d": pre_rel_mean,
                "relative_visitors_pct_post_28d": post_rel_mean,
                "relative_visitors_pct_point_change": post_rel_mean - pre_rel_mean,
                "relative_visitors_pct_change": safe_pct_change(pre_rel_mean, post_rel_mean),
                "p_value_relative_visitors": p_value,
                "is_significant": bool(pd.notna(p_value) and p_value < SIGNIFICANCE_LEVEL),
            }
        )


    if not evaluated_rows:
        return pd.DataFrame()

    evaluated = pd.DataFrame(evaluated_rows)
    return evaluated.sort_values(
        ["is_significant", "spike_ratio", "relative_visitors_pct_change"],
        ascending=[False, False, False],
    )


def choose_examples(evaluated: pd.DataFrame) -> pd.DataFrame:
    """Pick up to MAX_EXAMPLES rooms ensuring both positive and negative impact are shown.

    Selection criteria:
      1. Statistically significant (p < 0.05)
      2. tasks_14d ≥ MIN_TASKS_FOR_EXAMPLE  (huge burst) — relaxed for positive if needed
      3. |visitor_change_%| ≥ MIN_ABS_VISITOR_CHG  (clear impact)
    Ranked by impact_score = tasks_14d × |visitor_change_%|.
    Reserve at least 1 slot for positive and 1 for negative impact.
    """
    sig = evaluated.loc[evaluated["is_significant"]].copy()
    if sig.empty:
        return sig

    sig["abs_ratio_change"] = sig["relative_visitors_pct_change"].abs()
    sig["impact_score"] = sig["tasks_14d"] * sig["abs_ratio_change"]
    sig["direction"] = sig["relative_visitors_pct_change"].apply(
        lambda x: "positive" if x > 0 else "negative"
    )

    # strict pool (negative): big burst + meaningful visitor shift
    strict_neg = sig[
        (sig["tasks_14d"] >= MIN_TASKS_FOR_EXAMPLE)
        & (sig["abs_ratio_change"] >= MIN_ABS_VISITOR_CHG)
        & (sig["direction"] == "negative")
    ].sort_values("impact_score", ascending=False).copy()

    # positive pool: relaxed task threshold — only require meaningful visitor shift
    pos = sig[
        (sig["direction"] == "positive")
        & (sig["abs_ratio_change"] >= MIN_ABS_VISITOR_CHG)
    ].sort_values("impact_score", ascending=False).copy()

    neg = strict_neg

    # reserve exactly 1 slot for each direction when both are available
    if not pos.empty and not neg.empty:
        n_pos = min(1, len(pos))
        n_neg = min(MAX_EXAMPLES - n_pos, len(neg))
        chosen = pd.concat([neg.head(n_neg), pos.head(n_pos)], ignore_index=True)
    elif not neg.empty:
        chosen = neg.head(MAX_EXAMPLES)
    elif not pos.empty:
        chosen = pos.head(MAX_EXAMPLES)
    else:
        # fallback: any significant
        chosen = sig.sort_values("impact_score", ascending=False).head(MAX_EXAMPLES)

    # sort so the most significant (lowest p-value) appear on top
    chosen = chosen.sort_values("p_value_relative_visitors", ascending=True).reset_index(drop=True)
    return chosen


def plot_examples(
    relative_visitors: pd.DataFrame,
    examples: pd.DataFrame,
    output_path: Path,
    all_candidates: pd.DataFrame | None = None,
    tasks: pd.DataFrame | None = None,
) -> None:
    if examples.empty:
        return

    fig, axes = plt.subplots(len(examples), 1, figsize=(8, 3.8 * len(examples)), sharex=False)
    if len(examples) == 1:
        axes = [axes]

    for ax, (_, example) in zip(axes, examples.iterrows()):
        room_name = example["roomset_name_std"]
        room_df = relative_visitors.loc[
            relative_visitors["roomset_name_std"] == room_name
        ].sort_values("date").copy()
        change_date = pd.to_datetime(example["change_date"])

        # collect ALL burst dates for this room — every one gets a red line
        burst_dates: list[tuple[pd.Timestamp, int]] = [(change_date, int(example["tasks_14d"]))]
        if all_candidates is not None:
            room_bursts = all_candidates.loc[
                all_candidates["roomset_name_std"] == room_name
            ]
            for _, burst_row in room_bursts.iterrows():
                d = pd.to_datetime(burst_row["change_date"])
                if d != change_date:
                    burst_dates.append((d, int(burst_row["tasks_14d"])))
        burst_dates.sort(key=lambda x: x[0])

        # show full available timeline
        plot_min = room_df["date"].min()
        plot_max = room_df["date"].max()

        # --- pre/post windows: at least 14 days (2 full weeks) ---
        w_days = max(14, int(example.get("window_days_used", PREFERRED_WINDOW_DAYS)))
        pre_start = change_date - pd.Timedelta(days=w_days)
        post_end = change_date + pd.Timedelta(days=w_days)

        pre_mask = (room_df["date"] >= pre_start) & (room_df["date"] < change_date)
        post_mask = (room_df["date"] > change_date) & (room_df["date"] <= post_end)
        pre_vals = room_df.loc[pre_mask, "relative_visitors_pct"]
        post_vals = room_df.loc[post_mask, "relative_visitors_pct"]
        pre_mean = float(pre_vals.mean()) if len(pre_vals) > 0 else float("nan")
        post_mean = float(post_vals.mean()) if len(post_vals) > 0 else float("nan")

        # --- Left axis: daily ratio line + pre/post means ---
        ax.plot(
            room_df["date"], room_df["relative_visitors_pct"],
            linewidth=0.9, color="#4C78A8", alpha=0.55, zorder=3, label="Daily ratio",
        )
        # horizontal mean lines in pre & post
        if not np.isnan(pre_mean):
            ax.hlines(pre_mean, pre_start, change_date, colors="#2563EB", linewidth=2.0,
                      linestyle="-", label=f"Pre mean {pre_mean:.2f}%", zorder=4)
        if not np.isnan(post_mean):
            ax.hlines(post_mean, change_date, post_end, colors="#DC2626", linewidth=2.0,
                      linestyle="-", label=f"Post mean {post_mean:.2f}%", zorder=4)

        # shade pre/post
        ax.axvspan(pre_start, change_date, color="#93C5FD", alpha=0.12, label="Pre window")
        ax.axvspan(change_date, post_end, color="#FECACA", alpha=0.15, label="Post window")

        # draw a red line for every burst in this room
        for i, (bd, t14d) in enumerate(burst_dates):
            lw = 2.0 if bd == change_date else 1.3
            ls = "-" if bd == change_date else "--"
            alpha_v = 1.0 if bd == change_date else 0.7
            lbl = "Task burst" if i == 0 else None
            ax.axvline(bd, color="#FF6B6B", linewidth=lw, linestyle=ls, alpha=alpha_v, label=lbl)

        ax.set_ylabel("Visitors / store visitors (%)", fontsize=12, fontweight="bold")

        # --- Right axis: weekly task bar chart ---
        if tasks is not None:
            room_tasks = tasks.loc[tasks["roomset_name_std"] == room_name].copy()
            room_tasks = room_tasks.loc[
                (room_tasks["task_date"] >= plot_min) & (room_tasks["task_date"] <= plot_max)
            ].sort_values("task_date")

            all_weeks = pd.date_range(
                plot_min - pd.Timedelta(days=plot_min.weekday()),
                plot_max,
                freq="W-MON",
            )
            if not room_tasks.empty:
                room_tasks["week_start"] = room_tasks["task_date"].dt.to_period("W-SUN").dt.start_time
                weekly_tasks = room_tasks.groupby("week_start", as_index=False)["task_count"].sum()
            else:
                weekly_tasks = pd.DataFrame(columns=["week_start", "task_count"])
            weekly_tasks = (
                weekly_tasks.set_index("week_start")
                .reindex(all_weeks, fill_value=0)
                .rename_axis("week_start")
                .reset_index()
            )

            ax_r = ax.twinx()
            ax_r.bar(
                weekly_tasks["week_start"], weekly_tasks["task_count"],
                width=6.0, color="#FF6B6B", alpha=0.30, label="Weekly tasks",
                zorder=1,
            )
            ax_r.set_ylabel("Tasks / week", fontsize=12, fontweight="bold", color="#CC3333")
            ax_r.tick_params(axis="y", labelcolor="#CC3333")
            ax_r.set_ylim(bottom=0)
            ax.set_zorder(ax_r.get_zorder() + 1)
            ax.patch.set_visible(False)
            from matplotlib.patches import Patch
            task_patch = Patch(facecolor="#FF6B6B", alpha=0.30, label="Weekly tasks")
            handles, labels = ax.get_legend_handles_labels()
            handles.append(task_patch)
            labels.append("Weekly tasks")
            ax.legend(handles=handles, labels=labels, loc="upper left", ncols=4, fontsize=6.5)
        else:
            ax.legend(loc="upper left", ncols=4, fontsize=6.5)

        ax.grid(alpha=0.2)

        # --- Title: room | burst date | total tasks in burst | estimated lift ---
        total_tasks = int(example["total_tasks_burst"])
        if not np.isnan(pre_mean) and pre_mean > 0:
            lift_pct = 100.0 * (post_mean - pre_mean) / pre_mean
            lift_str = f"{lift_pct:+.1f}%"
        else:
            lift_pct = float("nan")
            lift_str = "N/A"
        ax.set_title(
            f"{room_name}  |  burst {change_date.date()}  |  "
            f"{total_tasks} tasks  |  "
            f"pre {pre_mean:.2f}% → post {post_mean:.2f}%  |  "
            f"lift {lift_str}",
            fontsize=9,
        )

    axes[-1].set_xlabel("Date")
    fig.tight_layout()
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def run(start_date: str, end_date: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    client = bigquery.Client(project=BIGQUERY_PROJECT)
    room_versions = fetch_fixa_room_versions(client, start_date=start_date, end_date=end_date)
    tasks = fetch_fixa_tasks(client, start_date=start_date, end_date=end_date)
    relative_visitors = build_relative_visitor_table(start_date=start_date, end_date=end_date)
    all_candidates = infer_reformat_candidates(tasks)  # all bursts, multiple per room

    if all_candidates.empty:
        print("No large roomset changes found with the current FIXA thresholds.")
        return

    # filter: only keep bursts from end of August 2025 onwards
    # AND ensure at least 2 full weeks of visitor data before and after the burst
    data_start = pd.Timestamp(start_date)
    data_end = pd.Timestamp(end_date)
    all_candidates = all_candidates.loc[
        (all_candidates["change_date"] >= pd.Timestamp(MIN_BURST_DATE))
        & (all_candidates["change_date"] >= data_start + pd.Timedelta(days=MIN_PRE_POST_DAYS))
        & (all_candidates["change_date"] <= data_end - pd.Timedelta(days=MIN_PRE_POST_DAYS))
    ].reset_index(drop=True)
    if all_candidates.empty:
        print(f"No bursts found from {MIN_BURST_DATE} with ≥{MIN_PRE_POST_DAYS}d pre/post margin.")
        return

    # keep only the strongest spike per roomset for evaluation
    candidates = all_candidates.drop_duplicates(subset=["roomset_name_std"], keep="first")
    evaluated = evaluate_candidates(candidates, relative_visitors)
    if evaluated.empty:
        print("Candidates were found, but not enough Ariadne daily data was available for the 28-day pre/post comparison.")
        return

    examples = choose_examples(evaluated)

    room_versions.to_csv(output_dir / "fixa_room_versions.csv", index=False)
    tasks.to_csv(output_dir / "fixa_tasks.csv", index=False)
    relative_visitors.to_csv(output_dir / "roomset_relative_visitors_daily.csv", index=False)
    evaluated.to_csv(output_dir / "reformat_candidates_with_significance.csv", index=False)
    examples.to_csv(output_dir / "reformat_significant_examples.csv", index=False)
    examples.to_csv(output_dir / "selected_candidates.csv", index=False)
    main_plot_path = output_dir / "reformat_visitors_pre_post_rescaled.png"
    plot_examples(relative_visitors, examples, main_plot_path, all_candidates=all_candidates, tasks=tasks)

    MAIN_VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    if not examples.empty:
        shutil.copy2(main_plot_path, MAIN_VISUALS_DIR / "03_reformat_visitors_pre_post_rescaled.png")

    print("=== FIXA maintenance impact analysis ===")
    print(evaluated.head(15).to_string(index=False))
    if not examples.empty:
        print("\n=== Significant positive / negative examples ===")
        print(examples.to_string(index=False))
    print(f"\nSaved: {output_dir / 'fixa_room_versions.csv'}")
    print(f"Saved: {output_dir / 'fixa_tasks.csv'}")
    print(f"Saved: {output_dir / 'roomset_relative_visitors_daily.csv'}")
    print(f"Saved: {output_dir / 'reformat_candidates_with_significance.csv'}")
    print(f"Saved: {output_dir / 'reformat_significant_examples.csv'}")
    print(f"Saved: {output_dir / 'selected_candidates.csv'}")
    if not examples.empty:
        print(f"Saved: {output_dir / 'reformat_visitors_pre_post_rescaled.png'}")
        print(f"Saved: {MAIN_VISUALS_DIR / '03_reformat_visitors_pre_post_rescaled.png'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find important FIXA roomset changes and test if relative visitors changed significantly.")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE, help="Analysis start date.")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE, help="Analysis end date.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Folder where outputs are saved.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(start_date=args.start_date, end_date=args.end_date, output_dir=args.output_dir)

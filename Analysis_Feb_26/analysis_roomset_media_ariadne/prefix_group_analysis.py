from __future__ import annotations

from pathlib import Path
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from analysis_common import (
    BASE_DIR, MAIN_VISUALS_DIR, PREFIX_COLORS, PREFIX_ORDER,
    fetch_area_durations, fetch_area_visitors, fetch_store_visitors,
    safe_pct_change, standardize_location,
)

INPUT_PATH = BASE_DIR / "outputs/monthly_roomset_analysis/monthly_roomset_metrics.csv"
OUTPUT_DIR = BASE_DIR / "outputs/prefix_group_analysis"
EXCLUDE_ROOMSETS = {"SE01"}


def build_prefix_summary(
    monthly: pd.DataFrame,
    store_daily: pd.DataFrame,
    durations_daily: pd.DataFrame,
) -> pd.DataFrame:
    store_daily = store_daily.copy()
    store_daily["month"] = store_daily["date"].dt.to_period("M").dt.to_timestamp()
    store_monthly = (
        store_daily.groupby("month", as_index=False)
        .agg(avg_store_visitors=("store_visitors", "mean"))
    )

    # aggregate durations to monthly per prefix group
    dur = durations_daily.copy()
    dur["month"] = dur["date"].dt.to_period("M").dt.to_timestamp()
    dur["prefix_group"] = dur["roomset_name_std"].str.extract(r"^([A-Za-z]+)", expand=False)
    dur = dur.loc[dur["prefix_group"].isin(PREFIX_ORDER)].copy()
    dur_monthly = (
        dur.groupby(["month", "prefix_group"], as_index=False)
        .agg(mean_avg_time=("avg_time", "mean"), std_avg_time=("avg_time", "std"))
    )
    dur_monthly["std_avg_time"] = dur_monthly["std_avg_time"].fillna(0.0)

    summary = (
        monthly.groupby(["month", "prefix_group"], as_index=False)
        .agg(
            roomset_count=("roomset_name_std", "nunique"),
            mean_avg_daily_visitors=("avg_daily_visitors", "mean"),
            std_avg_daily_visitors=("avg_daily_visitors", "std"),
        )
        .sort_values(["prefix_group", "month"])
    )
    summary = summary.merge(store_monthly, on="month", how="left")
    summary = summary.merge(dur_monthly, on=["month", "prefix_group"], how="left")
    summary["std_avg_daily_visitors"] = summary["std_avg_daily_visitors"].fillna(0.0)
    summary["lower_band"] = (summary["mean_avg_daily_visitors"] - summary["std_avg_daily_visitors"]).clip(lower=0)
    summary["upper_band"] = summary["mean_avg_daily_visitors"] + summary["std_avg_daily_visitors"]
    summary["mean_share_of_store_pct"] = 100 * summary["mean_avg_daily_visitors"] / summary["avg_store_visitors"].replace(0, pd.NA)
    summary["std_share_of_store_pct"] = 100 * summary["std_avg_daily_visitors"] / summary["avg_store_visitors"].replace(0, pd.NA)
    summary["lower_share_of_store_pct"] = (summary["mean_share_of_store_pct"] - summary["std_share_of_store_pct"].fillna(0)).clip(lower=0)
    summary["upper_share_of_store_pct"] = summary["mean_share_of_store_pct"] + summary["std_share_of_store_pct"].fillna(0)
    return summary


def build_prefix_overview(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for prefix, group_df in summary.groupby("prefix_group"):
        first_value = group_df.sort_values("month").iloc[0]["mean_avg_daily_visitors"]
        last_value = group_df.sort_values("month").iloc[-1]["mean_avg_daily_visitors"]
        rows.append(
            {
                "prefix_group": prefix,
                "months": group_df["month"].nunique(),
                "avg_roomset_count": group_df["roomset_count"].mean(),
                "avg_mean_daily_visitors": group_df["mean_avg_daily_visitors"].mean(),
                "avg_share_of_store_pct": group_df["mean_share_of_store_pct"].mean(),
                "trend_pct_from_first_to_last_month": safe_pct_change(first_value, last_value),
            }
        )
    return pd.DataFrame(rows).sort_values("avg_mean_daily_visitors", ascending=False)


def plot_prefix_summary(summary: pd.DataFrame, monthly: pd.DataFrame, output_path: Path) -> None:
    import matplotlib.dates as mdates

    fig, ax = plt.subplots(figsize=(8, 7))
    ax_right = ax.twinx()

    for prefix in PREFIX_ORDER:
        gdf = summary.loc[summary["prefix_group"] == prefix].sort_values("month")
        if gdf.empty:
            continue
        color = PREFIX_COLORS[prefix]

        # Left axis: avg daily visitors with ± 1 std band
        ax.plot(gdf["month"], gdf["mean_avg_daily_visitors"],
                marker="o", markersize=5, linewidth=2.2, color=color, label=prefix)
        ax.fill_between(gdf["month"], gdf["lower_band"], gdf["upper_band"],
                        color=color, alpha=0.10)

    # Rescale right axis so it coincides with left axis
    avg_store = summary["avg_store_visitors"].mean()
    factor = 100.0 / avg_store  # visitors → % conversion
    left_lo, left_hi = ax.get_ylim()
    ax_right.set_ylim(left_lo * factor, left_hi * factor)

    ax.set_ylabel("Avg daily visitors", fontsize=12, fontweight="bold")
    ax_right.set_ylabel("% of total store visitors", fontsize=12, fontweight="bold")
    ax.set_xlabel("Month", fontsize=10)
    ax.set_title("Prefix group evolution excluding SE01",
                 fontsize=11, fontweight="bold", pad=8)
    ax.legend(title="Prefix", loc="upper left", fontsize=9, title_fontsize=9,
              ncols=len(PREFIX_ORDER))
    ax.grid(axis="y", alpha=0.22)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.tick_params(axis="x", labelsize=9)
    ax.text(0.01, 0.02,
            "Solid line ± 1 std band.  Right axis = equivalent % of total store visitors.",
            transform=ax.transAxes, fontsize=8, color="#555")
    ax.spines["top"].set_visible(False)
    ax_right.spines["top"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def main(input_path: Path = INPUT_PATH, output_dir: Path = OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    monthly = pd.read_csv(input_path, parse_dates=["month"])
    monthly = monthly.loc[~monthly["roomset_name_std"].isin(EXCLUDE_ROOMSETS)].copy()
    monthly = monthly.loc[monthly["prefix_group"].isin(PREFIX_ORDER)].copy()
    monthly = monthly.loc[monthly["month"] >= "2025-09-01"].copy()

    start_date = monthly["month"].min().strftime("%Y-%m-%d")
    end_date = (monthly["month"].max() + pd.offsets.MonthEnd(1)).strftime("%Y-%m-%d")
    store_daily = fetch_store_visitors(start_date=start_date, end_date=end_date)
    durations_daily = fetch_area_durations(start_date=start_date, end_date=end_date)

    summary = build_prefix_summary(monthly, store_daily, durations_daily)
    overview = build_prefix_overview(summary)

    summary.to_csv(output_dir / "prefix_group_monthly_summary.csv", index=False)
    overview.to_csv(output_dir / "prefix_group_overview.csv", index=False)
    main_plot_path = output_dir / "prefix_group_evolution_with_band_dual_axis.png"
    plot_prefix_summary(summary, monthly, main_plot_path)

    MAIN_VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(main_plot_path, MAIN_VISUALS_DIR / "02_prefix_group_evolution_with_band_dual_axis.png")

    print("=== Prefix group analysis ===")
    print(summary.to_string(index=False))
    print("\n=== Prefix group overview ===")
    print(overview.to_string(index=False))
    print(f"\nSaved: {output_dir / 'prefix_group_monthly_summary.csv'}")
    print(f"Saved: {output_dir / 'prefix_group_overview.csv'}")
    print(f"Saved: {output_dir / 'prefix_group_evolution_with_band_dual_axis.png'}")
    print(f"Saved: {MAIN_VISUALS_DIR / '02_prefix_group_evolution_with_band_dual_axis.png'}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D

from analysis_common import (
    BASE_DIR,
    MAIN_VISUALS_DIR,
    PREFIX_COLORS,
    PREFIX_PLOT_ORDER,
    SHOWROOM_GEOJSON,
    fetch_area_visitors,
    infer_location_groups,
    load_floor_polygons,
    load_roomsets,
    month_start,
)

DEFAULT_START_DATE = "2025-05-01"
DEFAULT_END_DATE = "2026-02-28"
OUTPUT_DIR = BASE_DIR / "outputs/monthly_roomset_analysis"


def build_monthly_metrics(roomsets: pd.DataFrame, visitors: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = visitors.merge(
        roomsets[["roomset_name_std", "roomset_name", "prefix_group", "location_group", "path_progress", "area_m2"]],
        on="roomset_name_std",
        how="inner",
    )
    if daily.empty:
        raise ValueError("No Ariadne roomsets matched the showroom roomsets from the GeoJSON.")

    daily["month"] = month_start(daily["date"])
    monthly = (
        daily.groupby(
            ["month", "roomset_name_std", "roomset_name", "prefix_group", "location_group", "path_progress"],
            as_index=False,
        )
        .agg(
            avg_daily_visitors=("visitors", "mean"),
            total_monthly_visitors=("visitors", "sum"),
            days_seen=("date", "nunique"),
            area_m2=("area_m2", "mean"),
        )
        .sort_values(["month", "avg_daily_visitors"], ascending=[True, False])
    )
    return daily, monthly


def plot_showroom_groups(roomsets: pd.DataFrame, floor_polygons: pd.DataFrame, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 8))

    min_x, min_y, max_x, max_y = roomsets.total_bounds
    x_margin = (max_x - min_x) * 0.08
    y_margin = (max_y - min_y) * 0.08
    clipped_floor = floor_polygons.cx[min_x - x_margin:max_x + x_margin, min_y - y_margin:max_y + y_margin]
    clipped_floor.plot(ax=ax, color="#F3F4F6", edgecolor="#D1D5DB", linewidth=0.8)

    roomsets_plot = roomsets.copy()
    roomsets_plot = roomsets_plot.sort_values(["prefix_group", "roomset_name_std"]).reset_index(drop=True)

    for prefix_name in PREFIX_PLOT_ORDER:
        group_df = roomsets_plot.loc[roomsets_plot["prefix_group"] == prefix_name]
        if group_df.empty:
            continue

        color = PREFIX_COLORS.get(prefix_name, PREFIX_COLORS["OTHER"])
        group_df.plot(
            ax=ax,
            color=color,
            edgecolor=color,
            alpha=0.18,
            linewidth=1.0,
            zorder=2,
        )
        ax.scatter(
            group_df["centroid_x"],
            group_df["centroid_y"],
            s=60,
            color=color,
            edgecolors="#4B5563",
            linewidths=0.7,
            zorder=3,
        )
        for _, row in group_df.iterrows():
            ax.annotate(
                row["roomset_name_std"],
                (row["centroid_x"], row["centroid_y"]),
                fontsize=5.5,
                color="#1F2937",
                xytext=(2, 2),
                textcoords="offset points",
                zorder=4,
            )

    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            label=prefix_name,
            markerfacecolor=PREFIX_COLORS.get(prefix_name, PREFIX_COLORS["OTHER"]),
            markeredgecolor="#4B5563",
            markersize=8,
        )
        for prefix_name in PREFIX_PLOT_ORDER
        if prefix_name in set(roomsets_plot["prefix_group"])
    ]
    ax.legend(handles=legend_handles, title="Prefix", loc="upper right", frameon=True, fontsize=7, title_fontsize=8)
    ax.set_title("Roomsets on showroom floor", fontsize=12, pad=8)
    ax.grid(alpha=0.25)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.tick_params(axis="both", which="both", labelbottom=False, labelleft=False)
    ax.set_aspect("equal")
    ax.set_xlim(min_x - x_margin, max_x + x_margin)
    ax.set_ylim(min_y - y_margin, max_y + y_margin)
    fig.tight_layout()
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def run(start_date: str, end_date: str, geojson_path: Path, output_dir: Path, n_groups: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    floor_polygons = load_floor_polygons(geojson_path)
    roomsets = infer_location_groups(load_roomsets(geojson_path), n_groups=n_groups)
    visitors = fetch_area_visitors(start_date=start_date, end_date=end_date)
    daily, monthly = build_monthly_metrics(roomsets, visitors)

    roomsets.drop(columns="geometry").to_csv(output_dir / "roomset_location_groups.csv", index=False)
    daily.to_csv(output_dir / "roomset_daily_visitors.csv", index=False)
    monthly.to_csv(output_dir / "monthly_roomset_metrics.csv", index=False)
    main_plot_path = output_dir / "roomset_groups_on_showroom_floor.png"
    plot_showroom_groups(roomsets, floor_polygons, main_plot_path)

    MAIN_VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(main_plot_path, MAIN_VISUALS_DIR / "01_roomset_groups_on_showroom_floor.png")

    print("=== Showroom roomset extraction ===")
    print(f"Period: {start_date} to {end_date}")
    print(f"Roomsets plotted: {roomsets['roomset_name_std'].nunique()}")
    print(f"Saved: {output_dir / 'roomset_location_groups.csv'}")
    print(f"Saved: {output_dir / 'roomset_daily_visitors.csv'}")
    print(f"Saved: {output_dir / 'monthly_roomset_metrics.csv'}")
    print(f"Saved: {output_dir / 'roomset_groups_on_showroom_floor.png'}")
    print(f"Saved: {MAIN_VISUALS_DIR / '01_roomset_groups_on_showroom_floor.png'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the showroom roomset grouping plot and the monthly extraction table.")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE, help="Ariadne start date, for example 2025-05-01.")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE, help="Ariadne end date, for example 2026-02-28.")
    parser.add_argument("--geojson", type=Path, default=SHOWROOM_GEOJSON, help="Showroom GeoJSON file.")
    parser.add_argument("--n-groups", type=int, default=4, help="Number of ordered roomset groups to create.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Folder where the extracted data and plot are saved.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        start_date=args.start_date,
        end_date=args.end_date,
        geojson_path=args.geojson,
        output_dir=args.output_dir,
        n_groups=args.n_groups,
    )

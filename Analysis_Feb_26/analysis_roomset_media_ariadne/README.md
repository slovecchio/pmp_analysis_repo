# Clean analysis structure

This folder was reduced to the main scripts only.

## Main scripts

1. `monthly_roomset_analysis.py`
   - Builds the showroom roomset grouping table.
   - Creates `roomset_groups_on_showroom_floor.png` in the same point-label style as the old plot.
   - Saves the reusable daily and monthly roomset extraction tables.

2. `prefix_group_analysis.py`
   - Reads the monthly extraction table.
   - Creates `prefix_group_evolution_with_band_dual_axis.png`.
   - Saves simple prefix summary tables.

3. `weekly_roomset_trajectory_analysis.py`
   - Reads the local trajectory JSON files.
   - Reports the sample size, the share of users touching at least one roomset, and the average number of roomsets visited.
   - Saves the extraction tables and a simple plot.

4. `detect_room_reformat_impact.py`
   - Combines FIXA and Ariadne data.
   - Detects big roomset changes.
   - Tests whether relative visitors changed significantly before vs after the inferred change.
   - Saves one positive and one negative significant example when available.
   - Creates a simple business-oriented before/after chart.

## Shared helper

- `analysis_common.py`
  - Centralizes path handling, Ariadne access, GeoJSON loading, trajectory loading, and small helper functions.

## Main pictures folder

- `outputs/main_visuals`
   - `01_roomset_groups_on_showroom_floor.png`
   - `02_prefix_group_evolution_with_band_dual_axis.png`
   - `03_reformat_visitors_pre_post_rescaled.png`

This folder keeps the key pictures together in one place.

## Removed files

The following files were removed because they were exploratory or duplicated logic already covered by the main scripts:

- `deep_dive_starter.py`
- `plot_reformat_investigation.py`
- `refresh_weekly_outputs_with_area_api.py`

## Reproducible run order

From this folder, run:

1. `monthly_roomset_analysis.py`
2. `prefix_group_analysis.py`
3. `weekly_roomset_trajectory_analysis.py`
4. `detect_room_reformat_impact.py`

Each script writes extracted CSV files next to the one plot that matters for that analysis, and the key pictures are copied to `outputs/main_visuals`.

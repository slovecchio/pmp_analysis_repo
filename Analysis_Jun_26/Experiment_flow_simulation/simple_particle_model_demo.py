"""
Simple demo of the particle model from customer_flow_store_simulation.tex
(Section: Basic Particle Model and Velocity).

Purpose: understand the Euler time integration, each velocity component,
and how a single particle evolves step by step on a toy grid.
Run standalone — no external data needed.

Usage:
    python simple_particle_model_demo.py
    python simple_particle_model_demo.py --particle 3 --cell 5,2
"""

import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.collections import LineCollection

# ---------------------------------------------------------------------------
# 1. TOY STORE GEOMETRY (10x6 grid, 1 meter cells)
# ---------------------------------------------------------------------------
# Legend: 0 = wall/obstacle, 1 = walkable
BASE_STORE_MAP = np.array([
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 1, 1, 1, 1, 1, 1, 1, 1, 0],
    [0, 1, 1, 0, 0, 1, 1, 0, 1, 0],
    [0, 1, 1, 0, 0, 1, 1, 0, 1, 0],
    [0, 1, 1, 1, 1, 1, 1, 1, 1, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
], dtype=int)

ALTERNATE_STORE_MAP = np.array([
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 1, 1, 1, 1, 1, 1, 1, 1, 0],
    [0, 1, 0, 0, 1, 1, 1, 1, 1, 0],
    [0, 1, 1, 1, 1, 1, 0, 0, 1, 0],
    [0, 1, 1, 1, 1, 1, 1, 1, 1, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
], dtype=int)

STORE_MAP = BASE_STORE_MAP.copy()
NY, NX = STORE_MAP.shape
DX = 1.0  # meters per cell

# Entry at (1, 1), exit at (8, 4)
ENTRY = np.array([1.0, 1.0])
EXIT = np.array([8.0, 4.0])

# Attraction points are disabled in this toy configuration.
ATTRACTIONS = []

# Obstacles (centers of shelves for avoidance)
BASE_OBSTACLES = [
    {"position": np.array([3.5, 2.5]), "strength": 1.0},
    {"position": np.array([7.0, 2.5]), "strength": 1.0},
]

ALTERNATE_OBSTACLES = [
    {"position": np.array([2.5, 2.0]), "strength": 1.0},
    {"position": np.array([6.5, 3.0]), "strength": 1.0},
]

OBSTACLES = BASE_OBSTACLES


def wall_cell_centers(store_map: np.ndarray) -> np.ndarray:
    return np.array([
        [c, r]
        for r in range(store_map.shape[0])
        for c in range(store_map.shape[1])
        if store_map[r, c] == 0
    ], dtype=float)


WALL_CELL_CENTERS = wall_cell_centers(STORE_MAP)

# Main path: orthogonal polylines from entry to exit through each layout's shelf gap.
BASE_MAIN_PATH_POINTS = np.array([
    [1.0, 1.0],
    [5.0, 1.0],
    [5.0, 4.0],
    [8.0, 4.0],
])

ALTERNATE_MAIN_PATH_POINTS = np.array([
    [1.0, 1.0],
    [5.0, 1.0],
    [5.0, 4.0],
    [8.0, 4.0],
])

MAIN_PATH_POINTS = BASE_MAIN_PATH_POINTS.copy()


def set_layout(layout: str) -> None:
    global STORE_MAP, NY, NX, OBSTACLES, WALL_CELL_CENTERS, MAIN_PATH_POINTS

    if layout == "alternate":
        STORE_MAP = ALTERNATE_STORE_MAP.copy()
        OBSTACLES = ALTERNATE_OBSTACLES
        MAIN_PATH_POINTS = ALTERNATE_MAIN_PATH_POINTS.copy()
    else:
        STORE_MAP = BASE_STORE_MAP.copy()
        OBSTACLES = BASE_OBSTACLES
        MAIN_PATH_POINTS = BASE_MAIN_PATH_POINTS.copy()

    NY, NX = STORE_MAP.shape
    WALL_CELL_CENTERS = wall_cell_centers(STORE_MAP)


# ---------------------------------------------------------------------------
# 2. VELOCITY FIELD COMPONENTS (from the PDF equations)
# ---------------------------------------------------------------------------

def limit_norm(v: np.ndarray, max_norm: float) -> np.ndarray:
    norm = np.linalg.norm(v)
    if norm <= max_norm:
        return v
    return v * (max_norm / norm)


def v_path(x: np.ndarray, alpha: float = 3.0, path_pull: float = 0.8,
           off_path_distance: float = 2.5) -> np.ndarray:
    """
    Main path force: pulls the particle along and back toward the intended store route.
        v_path(x) = alpha * p(x)
    where p(x) combines route direction and correction toward the nearest path point.
    """
    # Find nearest segment on the main path
    best_tangent = np.zeros(2)
    best_projection = None
    best_dist = np.inf
    for i in range(len(MAIN_PATH_POINTS) - 1):
        a = MAIN_PATH_POINTS[i]
        b = MAIN_PATH_POINTS[i + 1]
        ab = b - a
        ab_len_sq = np.dot(ab, ab)
        if ab_len_sq < 1e-12:
            continue
        t = np.clip(np.dot(x - a, ab) / ab_len_sq, 0.0, 1.0)
        proj = a + t * ab
        d = np.linalg.norm(x - proj)
        if d < best_dist:
            best_dist = d
            tangent = ab / np.sqrt(ab_len_sq)
            best_tangent = tangent
            best_projection = proj

    if best_projection is None:
        return np.zeros(2)

    to_path = best_projection - x
    to_path_norm = np.linalg.norm(to_path)
    to_exit = EXIT - x
    to_exit_norm = np.linalg.norm(to_exit)

    if best_dist > off_path_distance:
        if to_exit_norm < to_path_norm:
            direction = to_exit
        else:
            direction = to_path
    else:
        pull_strength = min(best_dist / off_path_distance, 1.0) * path_pull
        direction = best_tangent + pull_strength * to_path

    norm = np.linalg.norm(direction)
    if norm < 1e-12:
        return alpha * best_tangent
    return alpha * direction / norm


def v_attraction(x: np.ndarray) -> np.ndarray:
    """
    Attraction to areas:
        v_attraction(x) = sum_k  beta_k * (a_k - x) / ||a_k - x||
    """
    total = np.zeros(2)
    for att in ATTRACTIONS:
        diff = att["position"] - x
        dist = np.linalg.norm(diff)
        if dist < 0.3:
            continue
        total += att["strength"] * diff / dist
    return total


def v_avoidance(x: np.ndarray) -> np.ndarray:
    """
    Obstacle avoidance (repulsion decays as 1/r^2):
        v_avoidance(x) = - sum_j  gamma_j * (o_j - x) / ||o_j - x||^2
    """
    total = np.zeros(2)
    for obs in OBSTACLES:
        diff = obs["position"] - x
        dist_sq = np.dot(diff, diff)
        if dist_sq < 0.01:
            dist_sq = 0.01
        total -= obs["strength"] * diff / dist_sq
    return total


def v_crowd(x: np.ndarray, all_positions: np.ndarray, lam: float = 0.5,
            max_speed: float = 2.0) -> np.ndarray:
    """
    Crowd pressure: move away from nearby particles (simplified).
        v_crowd(x, t) = -lambda * grad(rho)
    Here we approximate grad(rho) as the sum of unit vectors toward nearby particles.
    """
    total = np.zeros(2)
    for other in all_positions:
        diff = other - x
        dist = np.linalg.norm(diff)
        if dist < 0.01 or dist > 3.0:
            continue
        # gradient of density points toward other particles
        total += diff / dist
    # negative gradient = push away from crowd
    return limit_norm(-lam * total, max_speed)


def v_wall_avoidance(x: np.ndarray, distance: float = 1.25, strength: float = 1.8) -> np.ndarray:
    """Repel particles from nearby wall/shelf cells before they collide."""
    total = np.zeros(2)
    for wall_center in WALL_CELL_CENTERS:
        diff = x - wall_center
        dist = np.linalg.norm(diff)
        if dist < 1e-6 or dist > distance:
            continue
        total += strength * (distance - dist) / distance * diff / dist
    return total


def total_velocity(x: np.ndarray, all_positions: np.ndarray) -> np.ndarray:
    """
    Full velocity field:
        v(x,t) = v_path + v_attraction + v_avoidance + v_crowd + v_wall
    """
    v = (
        v_path(x)
        + v_attraction(x)
        + v_avoidance(x)
        + v_crowd(x, all_positions)
        + v_wall_avoidance(x)
    )
    return v


def gaussian_spawn_steps(n_particles: int, n_steps: int, peak_step: int = None,
                         spread_steps: float = None) -> np.ndarray:
    """Assign each particle a spawn step using a simple Gaussian inflow curve."""
    if peak_step is None:
        peak_step = n_steps // 2
    if spread_steps is None:
        spread_steps = max(1.0, n_steps / 6.0)

    steps = np.arange(n_steps)
    weights = np.exp(-0.5 * ((steps - peak_step) / spread_steps) ** 2)
    weights /= weights.sum()

    raw_counts = weights * n_particles
    counts = np.floor(raw_counts).astype(int)
    remainder = n_particles - counts.sum()
    if remainder > 0:
        order = np.argsort(raw_counts - counts)[::-1]
        counts[order[:remainder]] += 1

    return np.repeat(steps, counts)


# ---------------------------------------------------------------------------
# 3. BOUNDARY ENFORCEMENT
# ---------------------------------------------------------------------------

def is_walkable(x: np.ndarray) -> bool:
    col = int(round(x[0]))
    row = int(round(x[1]))
    if row < 0 or row >= NY or col < 0 or col >= NX:
        return False
    return STORE_MAP[row, col] == 1


def grid_cell(x: np.ndarray) -> tuple[int, int]:
    return int(round(x[1])), int(round(x[0]))


def clamp_to_walkable(x_old: np.ndarray, x_new: np.ndarray) -> np.ndarray:
    """If the new position is in a wall, reflect the remaining step from impact."""
    if is_walkable(x_new):
        return x_new

    step = x_new - x_old
    if np.linalg.norm(step) < 1e-12:
        return x_old.copy()

    last_walkable = x_old.copy()
    hit_point = x_new.copy()
    for fraction in np.linspace(0.05, 1.0, 20):
        candidate = x_old + fraction * step
        if is_walkable(candidate):
            last_walkable = candidate
        else:
            hit_point = candidate
            break

    row_old, col_old = grid_cell(last_walkable)
    row_hit, col_hit = grid_cell(hit_point)
    reflected_step = x_new - last_walkable
    reflected = reflected_step.copy()
    if col_hit != col_old:
        reflected[0] *= -1.0
    if row_hit != row_old:
        reflected[1] *= -1.0
    if np.allclose(reflected, reflected_step):
        reflected *= -1.0

    damping = 0.8
    reflected *= damping
    candidates = []
    for scale in (1.0, 0.75, 0.5, 0.25):
        candidates.extend([
            last_walkable + scale * reflected,
            last_walkable + scale * np.array([reflected[0], 0.0]),
            last_walkable + scale * np.array([0.0, reflected[1]]),
            x_old - scale * step,
        ])
    for scale in (0.75, 0.5, 0.25):
        candidates.extend([
            x_old - scale * step,
            x_old + scale * np.array([-step[0], step[1]]),
            x_old + scale * np.array([step[0], -step[1]]),
        ])

    for candidate in candidates:
        if is_walkable(candidate):
            return candidate

    if is_walkable(last_walkable):
        return last_walkable
    return x_old.copy()


# ---------------------------------------------------------------------------
# 4. EULER TIME INTEGRATION
# ---------------------------------------------------------------------------

def euler_step(x: np.ndarray, all_positions: np.ndarray, dt: float, sigma: float,
               rng: np.random.Generator) -> np.ndarray:
    """
    One Euler-Maruyama step (eq. from the PDF):

        X(t + dt) = X(t) + v(X, t) * dt + sigma * sqrt(dt) * epsilon

    where epsilon ~ N(0, I)
    """
    v = total_velocity(x, all_positions)
    noise = rng.standard_normal(2)

    x_proposed = x + v * dt + sigma * np.sqrt(dt) * noise
    x_new = clamp_to_walkable(x, x_proposed)
    return x_new, v, noise, x_proposed


# ---------------------------------------------------------------------------
# 5. SIMULATION
# ---------------------------------------------------------------------------

def has_exited(x: np.ndarray, exit_pos: np.ndarray, exit_radius: float = 1.0) -> bool:
    return float(np.linalg.norm(x - exit_pos)) < exit_radius


def run_simulation(n_particles: int, n_steps: int, dt: float, sigma: float,
                   seed: int = 42, verbose_particle: int = -1, verbose_cell: tuple = None,
                   wall_log: bool = False, wall_log_y: float = 3.5,
                   inflow: str = "gaussian"):
    rng = np.random.default_rng(seed)

    # Initialize particles at entry over time with small random offsets.
    positions = np.zeros((n_particles, 2), dtype=float)
    entry_offsets = rng.uniform(-0.3, 0.3, (n_particles, 2))
    if inflow == "instant":
        spawn_steps = np.zeros(n_particles, dtype=int)
    else:
        spawn_steps = gaussian_spawn_steps(n_particles, n_steps)
    active = np.zeros(n_particles, dtype=bool)
    spawned = np.zeros(n_particles, dtype=bool)
    trajectories = [
        [np.full(2, np.nan) for _ in range(n_steps + 1)]
        for _ in range(n_particles)
    ]
    # Cumulative visit count per grid cell (for heatmap)
    visit_counts = np.zeros((NY, NX), dtype=int)
    wall_log_entries = []

    print(f"\n{'='*70}")
    print(f"SIMULATION PARAMETERS")
    print(f"{'='*70}")
    print(f"  Particles     : {n_particles}")
    print(f"  Time steps    : {n_steps}")
    print(f"  dt            : {dt:.3f} min")
    print(f"  sigma (noise) : {sigma:.2f} m/sqrt(min)")
    print(f"  Total time    : {n_steps * dt:.1f} min")
    print(f"  Inflow        : {inflow}")
    print(f"  Entry         : {ENTRY}")
    print(f"  Exit          : {EXIT}")
    print(f"  Attractions   : {[a['label'] for a in ATTRACTIONS]}")
    print(f"{'='*70}\n")

    for step in range(n_steps):
        spawning = np.where(spawn_steps == step)[0]
        for i in spawning:
            positions[i] = ENTRY + entry_offsets[i]
            active[i] = True
            spawned[i] = True
            trajectories[i][step] = positions[i].copy()

        active_positions = positions[active]

        # Accumulate visits for all active particles this step
        for i in range(n_particles):
            if active[i]:
                col = int(round(positions[i][0]))
                row = int(round(positions[i][1]))
                if 0 <= row < NY and 0 <= col < NX:
                    visit_counts[row, col] += 1

        for i in range(n_particles):
            if not active[i]:
                continue

            x_old = positions[i].copy()

            # --- EULER STEP ---
            positions[i], v_step, noise_step, x_proposed = euler_step(
                positions[i], active_positions, dt, sigma, rng)
            wall_hit = not is_walkable(x_proposed)
            bounced = wall_hit and not np.allclose(positions[i], x_old)
            blocked = wall_hit and np.allclose(positions[i], x_old)

            # Check exit
            if has_exited(positions[i], EXIT):
                active[i] = False

            trajectories[i][step + 1] = positions[i].copy()

            # --- WALL LOG: all wall/shelf hits, plus particles near the top wall ---
            if wall_log and (wall_hit or x_old[1] >= wall_log_y):
                v_p = v_path(x_old)
                v_a = v_attraction(x_old)
                v_o = v_avoidance(x_old)
                v_c = v_crowd(x_old, active_positions)
                v_w = v_wall_avoidance(x_old)
                entry = {
                    "step": step, "particle": i,
                    "pos": x_old.copy(), "proposed": x_proposed.copy(),
                    "actual": positions[i].copy(), "wall_hit": wall_hit,
                    "bounced": bounced, "blocked": blocked,
                    "v_path": v_p, "v_attraction": v_a,
                    "v_avoidance": v_o, "v_crowd": v_c, "v_wall": v_w,
                    "v_total": v_step, "noise": noise_step,
                }
                wall_log_entries.append(entry)

            # --- VERBOSE: show decomposition for a specific particle ---
            if i == verbose_particle and step % 5 == 0:
                v_p = v_path(x_old)
                v_a = v_attraction(x_old)
                v_o = v_avoidance(x_old)
                v_c = v_crowd(x_old, active_positions)
                v_w = v_wall_avoidance(x_old)
                v_tot = v_p + v_a + v_o + v_c + v_w
                print(f"  Step {step:3d} | Particle {i} at ({x_old[0]:.2f}, {x_old[1]:.2f})")
                print(f"           v_path       = ({v_p[0]:+.3f}, {v_p[1]:+.3f})")
                print(f"           v_attraction = ({v_a[0]:+.3f}, {v_a[1]:+.3f})")
                print(f"           v_avoidance  = ({v_o[0]:+.3f}, {v_o[1]:+.3f})")
                print(f"           v_crowd      = ({v_c[0]:+.3f}, {v_c[1]:+.3f})")
                print(f"           v_wall       = ({v_w[0]:+.3f}, {v_w[1]:+.3f})")
                print(f"           v_total      = ({v_tot[0]:+.3f}, {v_tot[1]:+.3f})")
                print(f"           proposed     = ({x_proposed[0]:.2f}, {x_proposed[1]:.2f})")
                print(f"           actual       = ({positions[i][0]:.2f}, {positions[i][1]:.2f})")
                print(f"           wall_hit     = {wall_hit}")
                print(f"           bounced      = {bounced}")
                print(f"           blocked      = {blocked}")
                print()

        # --- VERBOSE: show density in a specific cell ---
        if verbose_cell is not None and step % 10 == 0:
            cx, cy = verbose_cell
            count = 0
            for j in range(n_particles):
                if not active[j]:
                    continue
                if abs(positions[j][0] - cx) < 0.5 and abs(positions[j][1] - cy) < 0.5:
                    count += 1
            print(f"  Step {step:3d} | Cell ({cx},{cy}) density: {count} particles")

        # Stop early if everyone exited
        if spawned.all() and not active.any():
            print(f"  All particles exited by step {step}")
            break

    # Final summary
    print(f"\n{'='*70}")
    print(f"RESULTS AFTER {n_steps} STEPS ({n_steps * dt:.1f} min)")
    print(f"{'='*70}")
    print(f"  Exited   : {(~active).sum()} / {n_particles}")
    print(f"  Remaining: {active.sum()}")

    # Density map
    density = np.zeros((NY, NX), dtype=int)
    for i in range(n_particles):
        if active[i]:
            col = int(round(positions[i][0]))
            row = int(round(positions[i][1]))
            if 0 <= row < NY and 0 <= col < NX:
                density[row, col] += 1

    print(f"\n  Final density grid (rows=y, cols=x):")
    print(f"  {'':4s}", end="")
    for c in range(NX):
        print(f"{c:3d}", end="")
    print()
    for r in range(NY):
        print(f"  y={r:1d} ", end="")
        for c in range(NX):
            if STORE_MAP[r, c] == 0:
                print("  #", end="")
            elif density[r, c] > 0:
                print(f"{density[r, c]:3d}", end="")
            else:
                print("  .", end="")
        print()

    # --- WALL LOG SUMMARY ---
    if wall_log and wall_log_entries:
        print(f"\n{'='*70}")
        print(f"WALL LOG: {len(wall_log_entries)} events near y >= {wall_log_y}")
        print(f"{'='*70}")
        wall_hit_count = sum(1 for e in wall_log_entries if e["wall_hit"])
        bounced_count = sum(1 for e in wall_log_entries if e["bounced"])
        blocked_count = sum(1 for e in wall_log_entries if e["blocked"])
        particles_near_wall = set(e["particle"] for e in wall_log_entries)
        print(f"  Unique particles near wall : {len(particles_near_wall)}")
        print(f"  Total near-wall events     : {len(wall_log_entries)}")
        print(f"  Wall hits                  : {wall_hit_count}  ({100*wall_hit_count/len(wall_log_entries):.0f}%)")
        print(f"  Bounced                    : {bounced_count}  ({100*bounced_count/len(wall_log_entries):.0f}%)")
        print(f"  Blocked (stayed in place)  : {blocked_count}  ({100*blocked_count/len(wall_log_entries):.0f}%)")
        print()

        # Average forces near wall
        avg_vp = np.mean([e["v_path"] for e in wall_log_entries], axis=0)
        avg_va = np.mean([e["v_attraction"] for e in wall_log_entries], axis=0)
        avg_vo = np.mean([e["v_avoidance"] for e in wall_log_entries], axis=0)
        avg_vc = np.mean([e["v_crowd"] for e in wall_log_entries], axis=0)
        avg_vw = np.mean([e["v_wall"] for e in wall_log_entries], axis=0)
        avg_vt = np.mean([e["v_total"] for e in wall_log_entries], axis=0)
        print(f"  Average forces near wall y >= {wall_log_y}:")
        print(f"    v_path       = ({avg_vp[0]:+.3f}, {avg_vp[1]:+.3f})")
        print(f"    v_attraction = ({avg_va[0]:+.3f}, {avg_va[1]:+.3f})")
        print(f"    v_avoidance  = ({avg_vo[0]:+.3f}, {avg_vo[1]:+.3f})")
        print(f"    v_crowd      = ({avg_vc[0]:+.3f}, {avg_vc[1]:+.3f})")
        print(f"    v_wall       = ({avg_vw[0]:+.3f}, {avg_vw[1]:+.3f})")
        print(f"    v_total      = ({avg_vt[0]:+.3f}, {avg_vt[1]:+.3f})")
        print()
        print(f"  DIAGNOSIS: v_total y-component is {'+' if avg_vt[1] > 0 else '-'}"
              f" => particles are pushed {'toward' if avg_vt[1] > 0 else 'away from'} the wall at y=5.")
        if avg_vt[1] > 0:
            print(f"  The bounce sends wall-hit particles back along the incoming vector.")
            print(f"  Main contributors pushing toward wall (positive y):")
            contributors = [
                ("v_path", avg_vp[1]), ("v_attraction", avg_va[1]),
                ("v_avoidance", avg_vo[1]), ("v_crowd", avg_vc[1]),
                ("v_wall", avg_vw[1]),
            ]
            contributors.sort(key=lambda c: c[1], reverse=True)
            for name, val in contributors:
                if val > 0.01:
                    print(f"    {name:16s} y = {val:+.3f}")
        print()

        # Show a few example events
        sample = wall_log_entries[:5]
        print(f"  First {len(sample)} near-wall events:")
        for e in sample:
            if e["bounced"]:
                tag = "BOUNCED"
            elif e["blocked"]:
                tag = "BLOCKED"
            elif e["wall_hit"]:
                tag = "wall-hit"
            else:
                tag = "accepted"
            print(f"    Step {e['step']:3d} P{e['particle']:2d}  "
                  f"pos=({e['pos'][0]:.2f},{e['pos'][1]:.2f})  "
                  f"proposed=({e['proposed'][0]:.2f},{e['proposed'][1]:.2f})  "
                  f"actual=({e['actual'][0]:.2f},{e['actual'][1]:.2f})  [{tag}]")
            print(f"      v_path=({e['v_path'][0]:+.2f},{e['v_path'][1]:+.2f})  "
                  f"v_attr=({e['v_attraction'][0]:+.2f},{e['v_attraction'][1]:+.2f})  "
                  f"v_avoid=({e['v_avoidance'][0]:+.2f},{e['v_avoidance'][1]:+.2f})  "
                  f"v_crowd=({e['v_crowd'][0]:+.2f},{e['v_crowd'][1]:+.2f})  "
                f"v_wall=({e['v_wall'][0]:+.2f},{e['v_wall'][1]:+.2f})  "
                  f"noise=({e['noise'][0]:+.2f},{e['noise'][1]:+.2f})")
        print()

    return positions, active, trajectories, visit_counts


# ---------------------------------------------------------------------------
# 6. PLOT
# ---------------------------------------------------------------------------

def plot_trajectories(trajectories, active, out_path: str = "particle_trajectories.png"):
    fig, ax = plt.subplots(figsize=(10, 6))

    # Draw store layout: walls as dark grey, walkable as light
    for r in range(NY):
        for c in range(NX):
            color = "#d0d0d0" if STORE_MAP[r, c] == 1 else "#3a3a3a"
            ax.add_patch(plt.Rectangle((c - 0.5, r - 0.5), 1, 1,
                                       facecolor=color, edgecolor="white", lw=0.5))

    # Main path
    ax.plot(MAIN_PATH_POINTS[:, 0], MAIN_PATH_POINTS[:, 1],
            "--", color="#888888", lw=1.5, label="main path", zorder=2)

    # Attractions
    for att in ATTRACTIONS:
        ax.plot(*att["position"], "s", color="#e07b39", ms=10, zorder=5)
        ax.annotate(att["label"], att["position"], fontsize=7,
                    ha="center", va="bottom", xytext=(0, 6),
                    textcoords="offset points", color="#e07b39")

    # Entry / Exit
    ax.plot(*ENTRY, "o", color="green", ms=10, zorder=5, label="entry")
    ax.plot(*EXIT, "X", color="red", ms=11, zorder=5, label="exit")

    # Particle trajectories with fading colour along time
    cmap = plt.colormaps["tab10"]
    for i, traj in enumerate(trajectories):
        pts = np.array(traj)
        pts = pts[np.isfinite(pts).all(axis=1)]
        if len(pts) < 2:
            continue
        segments = np.stack([pts[:-1], pts[1:]], axis=1)
        alphas = np.linspace(0.15, 0.9, len(segments))
        color = cmap(i % 10)
        colors = [(color[0], color[1], color[2], a) for a in alphas]
        lc = LineCollection(segments, colors=colors, lw=1.4, zorder=3)
        ax.add_collection(lc)
        # final position marker
        marker = "o" if active[i] else "x"
        ax.plot(pts[-1, 0], pts[-1, 1], marker, color=color, ms=6, zorder=4)

    ax.set_xlim(-0.5, NX - 0.5)
    ax.set_ylim(-0.5, NY - 0.5)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("Particle trajectories on toy store layout")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"\n  Plot saved to {out_path}")


def _draw_store(ax):
    """Draw the store layout background on an axes."""
    for r in range(NY):
        for c in range(NX):
            color = "#d0d0d0" if STORE_MAP[r, c] == 1 else "#3a3a3a"
            ax.add_patch(plt.Rectangle((c - 0.5, r - 0.5), 1, 1,
                                       facecolor=color, edgecolor="white", lw=0.5))
    ax.plot(MAIN_PATH_POINTS[:, 0], MAIN_PATH_POINTS[:, 1],
            "--", color="#888888", lw=1.5, zorder=2)
    for att in ATTRACTIONS:
        ax.plot(*att["position"], "s", color="#e07b39", ms=10, zorder=5)
        ax.annotate(att["label"], att["position"], fontsize=7,
                    ha="center", va="bottom", xytext=(0, 6),
                    textcoords="offset points", color="#e07b39")
    ax.plot(*ENTRY, "o", color="green", ms=10, zorder=5)
    ax.plot(*EXIT, "X", color="red", ms=11, zorder=5)
    ax.set_xlim(-0.5, NX - 0.5)
    ax.set_ylim(-0.5, NY - 0.5)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")


def plot_heatmap(visit_counts: np.ndarray, out_path: str = "density_heatmap.png"):
    fig, ax = plt.subplots(figsize=(10, 6))
    masked = np.ma.masked_where(STORE_MAP == 0, visit_counts.astype(float))
    im = ax.imshow(masked, origin="lower", cmap="hot", interpolation="nearest",
                   extent=(-0.5, NX - 0.5, -0.5, NY - 0.5), aspect="equal")
    # Draw wall outlines
    for r in range(NY):
        for c in range(NX):
            if STORE_MAP[r, c] == 0:
                ax.add_patch(plt.Rectangle((c - 0.5, r - 0.5), 1, 1,
                                           facecolor="#3a3a3a", edgecolor="white", lw=0.3))
    ax.plot(*ENTRY, "o", color="green", ms=9, zorder=5)
    ax.plot(*EXIT, "X", color="cyan", ms=10, zorder=5)
    for att in ATTRACTIONS:
        ax.plot(*att["position"], "s", color="#e07b39", ms=9, zorder=5)
    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("cumulative visits (particle×steps)")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("Heatmap: cumulative particle visits per grid cell")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"\n  Heatmap saved to {out_path}")


def animate_trajectories(trajectories, active, dt: float,
                         out_path: str = "particle_simulation.gif",
                         fps: int = 8, trail: int = 8, max_frames: int = None):
    n_frames = max(len(t) for t in trajectories)
    frame_indices = np.arange(n_frames)
    if max_frames is not None and n_frames > max_frames:
        frame_indices = np.linspace(0, n_frames - 1, max_frames, dtype=int)
    cmap = plt.colormaps["tab10"]
    n_particles = len(trajectories)

    fig, ax = plt.subplots(figsize=(10, 6))
    _draw_store(ax)
    ax.set_title("t = 0.0 min")

    dots = []
    trails = []
    for i in range(n_particles):
        color = cmap(i % 10)
        dot, = ax.plot([], [], "o", color=color, ms=7, zorder=6)
        lc = LineCollection([], colors=[], lw=1.4, zorder=3)
        ax.add_collection(lc)
        dots.append(dot)
        trails.append(lc)

    def update(frame):
        ax.set_title(f"t = {frame * dt:.1f} min")
        for i in range(n_particles):
            pts = np.array(trajectories[i])
            if frame >= len(pts):
                if not active[i]:
                    dots[i].set_data([], [])
                    trails[i].set_segments([])
                continue
            if not np.isfinite(pts[frame]).all():
                dots[i].set_data([], [])
                trails[i].set_segments([])
                continue
            dots[i].set_data([pts[frame, 0]], [pts[frame, 1]])
            start = max(0, frame - trail)
            seg_pts = pts[start:frame + 1]
            seg_pts = seg_pts[np.isfinite(seg_pts).all(axis=1)]
            if len(seg_pts) >= 2:
                segs = np.stack([seg_pts[:-1], seg_pts[1:]], axis=1)
                color = cmap(i % 10)
                alphas = np.linspace(0.15, 0.9, len(segs))
                colors = [(color[0], color[1], color[2], a) for a in alphas]
                trails[i].set_segments(segs)
                trails[i].set_colors(colors)
            else:
                trails[i].set_segments([])
        return dots + trails

    anim = FuncAnimation(fig, update, frames=frame_indices, interval=1000 // fps, blit=False)
    anim.save(out_path, writer=PillowWriter(fps=fps))
    plt.close(fig)
    print(f"\n  GIF saved to {out_path}")


# ---------------------------------------------------------------------------
# 7. MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Simple particle model demo (PDF: Basic Particle Model and Velocity)")
    parser.add_argument("--particles", type=int, default=8)
    parser.add_argument("--steps", type=int, default=60)
    parser.add_argument("--dt", type=float, default=0.3, help="time step in minutes")
    parser.add_argument("--sigma", type=float, default=1.2, help="noise strength m/sqrt(min)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--inflow", choices=["instant", "gaussian"], default="gaussian",
                        help="particle arrival pattern over simulation time")
    parser.add_argument("--layout", choices=["base", "alternate"], default="base",
                        help="toy store shelf/wall layout")
    parser.add_argument("--particle", type=int, default=0,
                        help="index of the particle to trace in detail (-1 = none)")
    parser.add_argument("--cell", type=str, default=None,
                        help="cell to monitor, format: col,row e.g. 5,2")
    parser.add_argument("--plot", action="store_true",
                        help="save a trajectory plot as PNG")
    parser.add_argument("--plot-out", type=str, default="particle_trajectories.png",
                        help="output filename for the plot")
    parser.add_argument("--gif", action="store_true",
                        help="save an animated GIF of the simulation")
    parser.add_argument("--gif-out", type=str, default="particle_simulation.gif",
                        help="output filename for the GIF")
    parser.add_argument("--fps", type=int, default=8, help="GIF frames per second")
    parser.add_argument("--trail", type=int, default=8,
                        help="number of recent steps shown as trail in GIF")
    parser.add_argument("--max-gif-frames", type=int, default=None,
                        help="maximum frames to save in the GIF")
    parser.add_argument("--heatmap", action="store_true",
                        help="save a density heatmap PNG")
    parser.add_argument("--heatmap-out", type=str, default="density_heatmap.png",
                        help="output filename for the heatmap")
    parser.add_argument("--wall-log", action="store_true",
                        help="log detailed forces for particles near y=4 wall")
    args = parser.parse_args()

    set_layout(args.layout)

    verbose_cell = None
    if args.cell:
        parts = args.cell.split(",")
        verbose_cell = (int(parts[0]), int(parts[1]))

    print("\n" + "="*70)
    print(f"STORE MAP [{args.layout}] (# = wall, . = walkable, E = entry, X = exit, A = attraction)")
    print("="*70)
    for r in range(NY):
        row_str = ""
        for c in range(NX):
            pos = np.array([c, r], dtype=float)
            if np.linalg.norm(pos - ENTRY) < 0.5:
                row_str += " E"
            elif np.linalg.norm(pos - EXIT) < 0.5:
                row_str += " X"
            elif any(np.linalg.norm(pos - a["position"]) < 0.8 for a in ATTRACTIONS):
                row_str += " A"
            elif STORE_MAP[r, c] == 0:
                row_str += " #"
            else:
                row_str += " ."
        print(f"  y={r} {row_str}")
    print()

    print("MODEL EQUATIONS (from the PDF):")
    print("  X(t+dt) = X(t) + v(X,t)*dt + sigma*sqrt(dt)*epsilon")
    print("  v(x,t)  = v_path + v_attraction + v_avoidance + v_crowd + v_wall")
    print()
    print("ASSUMPTIONS:")
    print("  - Euler-Maruyama integration (first order, fixed dt)")
    print("  - Gaussian noise epsilon ~ N(0, I)")
    print("  - Wall bounce: if new position is in obstacle, reflect the trajectory vector")
    print("  - v_path: unit tangent along nearest path segment, scaled by alpha")
    print("  - v_attraction: unit vector toward each attractor, scaled by beta_k")
    print("  - v_avoidance: repulsion decaying as 1/r^2 from obstacles")
    print("  - v_crowd: capped repulsion from nearby particles (approx. -grad(rho))")
    print("  - v_wall: short-range repulsion from nearby wall/shelf grid cells")
    print("  - Exit condition: particle within 1m of exit point")
    print()

    positions, active, trajectories, visit_counts = run_simulation(
        n_particles=args.particles,
        n_steps=args.steps,
        dt=args.dt,
        sigma=args.sigma,
        seed=args.seed,
        verbose_particle=args.particle,
        verbose_cell=verbose_cell,
        wall_log=args.wall_log,
        inflow=args.inflow,
    )

    if args.plot:
        plot_trajectories(trajectories, active, out_path=args.plot_out)

    if args.gif:
        animate_trajectories(trajectories, active, dt=args.dt,
                             out_path=args.gif_out, fps=args.fps, trail=args.trail,
                             max_frames=args.max_gif_frames)

    if args.heatmap:
        plot_heatmap(visit_counts, out_path=args.heatmap_out)


if __name__ == "__main__":
    main()

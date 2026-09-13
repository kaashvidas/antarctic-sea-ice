"""
Module 3 — route optimizer.

Not ML — a search over a hand-defined cost function on a grid, combining:
  - distance (always some cost, even in open water)
  - sea-ice concentration forecast (Module 1 output)
  - iceberg drift probability cones (Module 2 output)
  - bathymetry (IBCSO v2 / GEBCO Southern Ocean) as a hard/soft feasibility
    constraint

Per the README's Phase 4 and cut-order notes: implement the isochrone
method if time allows (more defensible — cite the isochrone paper in the
README as "how real ship-routing software works"), but have the A*
fallback below ready as insurance. ALWAYS compute and show both the
optimized route and the naive shortest-distance route side by side —
called out as the single best demo moment in this project.
"""

import heapq

import numpy as np


def build_cost_grid_stack(seaice_forecast_stack, iceberg_risk_stack, bathymetry, weights: dict = None) -> np.ndarray:
    """
    Day-by-day version of build_cost_grid() -- one real cost grid per
    forecast day, from real per-day sea-ice concentration
    (src.integration.pipeline.get_seaice_concentration()) and real
    per-day iceberg drift risk (pipeline.rasterize_iceberg_risk_per_day()),
    not a single static snapshot. This is what isochrone_route() needs to
    actually reason about *when* the ship would be somewhere, not just
    where -- a route arriving at a cell on day 6 gets judged against day
    6's real forecast, not day 0's.
    """
    n_days = min(seaice_forecast_stack.shape[0], iceberg_risk_stack.shape[0])
    return np.stack([
        build_cost_grid(seaice_forecast_stack[d], iceberg_risk_stack[d], bathymetry, weights=weights)
        for d in range(n_days)
    ], axis=0)


def build_cost_grid(seaice_forecast, iceberg_risk, bathymetry, weights: dict = None) -> np.ndarray:
    """
    Combine the three risk/feasibility layers into a single cost grid for
    a given forecast day.

    Parameters
    ----------
    seaice_forecast : 2-D array, concentration 0-1, for this forecast day
    iceberg_risk : 2-D array, probability/density of iceberg presence,
        derived from Module 2's drift cones for this forecast day
    bathymetry : 2-D array, depth in meters (negative = below sea level);
        used to flag infeasible (too-shallow / grounded) cells
    weights : optional override of the default risk weighting — expose
        this as a slider in the dashboard eventually so the tradeoff
        between fuel efficiency and risk-aversion is visible and
        adjustable, not fixed and hidden

    Returns a cost grid where higher = worse; infeasible cells should be
    np.inf so the search never routes through them.

    NOTE: the README is explicit that this cost function is *synthesized*,
    not calibrated against real fuel-consumption data (none exists
    publicly for polar-class research vessels) — state that plainly
    wherever this function's output is presented, don't imply it's
    empirically validated.
    """
    weights = weights or {"distance": 1.0, "seaice": 3.0, "iceberg": 5.0}

    base_cost = np.ones_like(seaice_forecast) * weights["distance"]
    ice_cost = seaice_forecast * weights["seaice"]
    iceberg_cost = iceberg_risk * weights["iceberg"]

    cost = base_cost + ice_cost + iceberg_cost
    cost = np.where(bathymetry > -10, np.inf, cost)  # too shallow / grounded -> infeasible
    return cost


def astar_route(cost_grid: np.ndarray, start: tuple, goal: tuple) -> list:
    """
    Simple fallback: A* over the cost grid with an admissible Euclidean
    heuristic. Cheaper to implement correctly under time pressure than
    the isochrone method — use this first to get an end-to-end Phase 4
    pipeline working, then attempt isochrone_route() below if time
    remains, per the README's cut order.

    start, goal : (row, col) grid indices
    Returns a list of (row, col) points from start to goal.
    """
    def heuristic(a, b):
        return np.hypot(a[0] - b[0], a[1] - b[1])

    open_set = [(0, start)]
    came_from = {}
    g_score = {start: 0}

    neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]

    while open_set:
        _, current = heapq.heappop(open_set)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return path[::-1]

        for dr, dc in neighbors:
            neighbor = (current[0] + dr, current[1] + dc)
            if not (0 <= neighbor[0] < cost_grid.shape[0] and 0 <= neighbor[1] < cost_grid.shape[1]):
                continue
            step_cost = cost_grid[neighbor]
            if not np.isfinite(step_cost):
                continue

            tentative_g = g_score[current] + step_cost
            if tentative_g < g_score.get(neighbor, np.inf):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score = tentative_g + heuristic(neighbor, goal)
                heapq.heappush(open_set, (f_score, neighbor))

    raise ValueError("No feasible path found — check for a disconnected/all-infeasible cost grid.")


def naive_route(start: tuple, goal: tuple) -> list:
    """Pure shortest-distance path ignoring all risk — the comparison
    baseline shown alongside the optimized route. A simple straight-line
    (Bresenham-style) grid line is enough; it doesn't need to be
    feasibility-checked since its whole point is to show what NOT
    accounting for risk would have done."""
    r0, c0 = start
    r1, c1 = goal
    n_steps = int(max(abs(r1 - r0), abs(c1 - c0)))
    return [
        (round(r0 + (r1 - r0) * t / n_steps), round(c0 + (c1 - c0) * t / n_steps))
        for t in range(n_steps + 1)
    ]


def isochrone_route(cost_grid_by_day: np.ndarray, bathymetry: np.ndarray, start: tuple, goal: tuple,
                     vessel_speed_kmh: float, resolution_km: float,
                     time_step_hours: float = 6.0, max_days: int = None) -> tuple:
    """
    Real time-stepped wavefront (isochrone) routing, per the isochrone
    paper cited in README.md: expands outward from `start` in sub-daily
    steps, each step limited to however far the vessel can actually
    travel at vessel_speed_kmh in time_step_hours, using that step's REAL
    day-specific cost grid -- not one static snapshot for the whole
    voyage like astar_route(). A route arriving at a cell on day 6 is
    judged against day 6's real sea-ice/iceberg-risk forecast, not day
    0's; this is the entire point of the isochrone method over plain A*.

    Parameters
    ----------
    cost_grid_by_day : (n_days, n_lat, n_lon), from build_cost_grid_stack()
    bathymetry : (n_lat, n_lon) -- used to feasibility-check every
        intermediate cell a multi-cell hop passes over, since a hop can
        skip several cells at once and build_cost_grid's np.inf marking
        only guarantees the ENDPOINTS were checked when the stack was built
    start, goal : (row, col) grid indices
    vessel_speed_kmh, resolution_km : real km/h and real km-per-grid-cell
        (src.utils.grid.GRID.resolution_deg * 111, the lat-direction
        conversion -- used for both directions as a deliberately
        conservative approximation, since a degree of longitude is
        physically shorter than a degree of latitude at these southern
        latitudes; this slightly under-estimates how far the ship can
        reach east-west per step rather than over-estimating it)
    max_days : stop expanding past this many days; defaults to the
        forecast horizon plus 3 days of slack (any time beyond
        cost_grid_by_day's real coverage reuses its last available day,
        same persistence-extension convention as the rest of the
        pipeline once real data runs out)

    Returns (path, arrival_hours) where path is a list of (row, col) from
    start to goal and arrival_hours is the real total travel time.

    Known simplification (disclosed, not hidden): the search keeps only
    the single best (lowest-cost) arrival at each grid cell, not one per
    (cell, day) pair. That's the right choice for "cheapest route" but
    means the algorithm won't consider deliberately waiting somewhere to
    catch better conditions later -- a genuine isochrone/weather-routing
    system for a real vessel might do that; this one doesn't yet.
    """
    n_days, n_lat, n_lon = cost_grid_by_day.shape
    max_days = max_days if max_days is not None else n_days + 3

    max_step_km = vessel_speed_kmh * time_step_hours
    max_step_cells = max(1, int(np.ceil(max_step_km / resolution_km)))

    # Candidate hop offsets within one time step's real reach.
    offsets = []
    for dr in range(-max_step_cells, max_step_cells + 1):
        for dc in range(-max_step_cells, max_step_cells + 1):
            if dr == 0 and dc == 0:
                continue
            cell_dist = float(np.hypot(dr, dc))
            if cell_dist <= max_step_cells:
                offsets.append((dr, dc, cell_dist))

    def day_grid(hours_elapsed):
        day = min(int(hours_elapsed // 24), n_days - 1)
        return cost_grid_by_day[day]

    def line_cost_and_feasible(r0, c0, r1, c1, grid):
        """Sample the straight-line hop; infeasible if any sampled cell
        (grid cost OR raw bathymetry) is inf/too-shallow/out of bounds.

        Deliberately skips t=0 (the ORIGIN cell, i.e. wherever the ship
        already is) -- matching astar_route()'s own convention of never
        cost-checking the start cell, only cells being moved INTO. A real
        start point can land on a cell that's marginal/infeasible for a
        given vessel's ice-class cutoff (the snapped-to-open-water start
        just needs bathymetry clearance, not a guarantee of being under
        every vessel's safe ice threshold too) -- the ship still needs to
        be ABLE to depart from wherever it actually starts.
        """
        n_samples = max(2, int(np.hypot(r1 - r0, c1 - c0)) + 1)
        costs = []
        for t in np.linspace(0.0, 1.0, n_samples):
            if t == 0.0:
                continue
            r = int(round(r0 + (r1 - r0) * t))
            c = int(round(c0 + (c1 - c0) * t))
            if not (0 <= r < n_lat and 0 <= c < n_lon):
                return None, False
            if bathymetry[r, c] > -10:
                return None, False
            v = grid[r, c]
            if not np.isfinite(v):
                return None, False
            costs.append(v)
        return float(np.mean(costs)), True

    frontier = [(0.0, 0.0, start)]  # (cumulative_cost, hours_elapsed, cell)
    best_cost = {start: 0.0}
    came_from = {}
    arrival_hours = {start: 0.0}

    while frontier:
        cum_cost, hours, current = heapq.heappop(frontier)
        if cum_cost > best_cost.get(current, np.inf):
            continue  # stale queue entry, a cheaper route to `current` was already found
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return path[::-1], arrival_hours[goal]
        if hours >= max_days * 24:
            continue

        grid = day_grid(hours)
        r0, c0 = current
        for dr, dc, cell_dist in offsets:
            r1, c1 = r0 + dr, c0 + dc
            if not (0 <= r1 < n_lat and 0 <= c1 < n_lon):
                continue
            mean_cost, feasible = line_cost_and_feasible(r0, c0, r1, c1, grid)
            if not feasible:
                continue
            new_cost = cum_cost + mean_cost * cell_dist
            new_time = hours + time_step_hours
            if new_cost < best_cost.get((r1, c1), np.inf):
                best_cost[(r1, c1)] = new_cost
                arrival_hours[(r1, c1)] = new_time
                came_from[(r1, c1)] = current
                heapq.heappush(frontier, (new_cost, new_time, (r1, c1)))

    raise ValueError(
        "No feasible isochrone path found within the day budget — check for a "
        "disconnected/all-infeasible cost grid, or the goal may be unreachable at "
        "this vessel speed within max_days."
    )

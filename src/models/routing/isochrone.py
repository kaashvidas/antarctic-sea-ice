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


def isochrone_route(cost_grid: np.ndarray, start: tuple, goal: tuple, time_step: float = 1.0) -> list:
    """
    Stretch goal: proper isochrone method (expanding a reachable-set
    wavefront under the cost field, per the isochrone paper in the
    README), which better represents how real ship-routing software
    reasons about time-varying conditions than a static-grid A* does.

    Only attempt this after astar_route() is working end-to-end — per the
    README's cut order, isochrone is the first thing to fall back away
    from under time pressure, and a complete A* pipeline beats an
    incomplete isochrone one.
    """
    raise NotImplementedError(
        "Implement after astar_route() works end-to-end; see the isochrone "
        "paper cited in README.md for the wavefront-expansion algorithm."
    )

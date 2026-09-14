"""
On-demand journey planning: given a start point, destination, departure
time, and vessel details, compute a real optimized-vs-naive route for
THAT specific journey (not the fixed demo scenario in pipeline.py) and
build a detailed voyage report around it — day-by-day conditions along
the route, iceberg closest-approach warnings, and the risk delta between
the optimized and naive paths.

Kept separate from pipeline.py: pipeline.py produces the precomputed
background map layers (sea-ice overlay images, default iceberg tracks),
run once offline. This module runs synchronously per API request instead,
since an arbitrary user-chosen start/goal can't be precomputed. Reuses
every piece of real physics/data machinery pipeline.py already has —
nothing here re-implements iceberg loading, drift, bathymetry, or
routing.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.utils.grid import GRID, lat_lon_mesh, latlon_to_index, index_to_latlon  # noqa: E402
from src.data.preprocess import regrid_bathymetry  # noqa: E402
from src.models.iceberg_drift.wagner_model import haversine_km  # noqa: E402
from src.models.routing.isochrone import (  # noqa: E402
    build_cost_grid, build_cost_grid_stack, astar_route, isochrone_route, naive_route,
)
from src.integration.pipeline import (  # noqa: E402
    BATHY_TIF,
    load_iceberg_cluster, run_drift_ensemble, rasterize_iceberg_risk_per_day,
    get_seaice_concentration, get_forcing_fields, find_open_water,
)

RESOLUTION_KM = GRID.resolution_deg * 111.0  # lat-direction km/cell -- see isochrone_route()'s own docstring

# Vessel ice class -> how much sea-ice concentration it can safely operate
# in, and how heavily the router should weight ice avoidance for it. Not a
# regulatory classification table (IACS Polar Class rules are far more
# detailed) -- a deliberately simple, disclosed stand-in so "vessel
# details" is a real input to the route rather than a cosmetic field.
#
# Two thresholds, not one:
#   max_safe_concentration      -- beyond this, cost escalates steeply
#                                   (slower, riskier transit) but the cell
#                                   is still reachable.
#   hard_infeasible_concentration -- true absolute wall (np.inf): only
#                                   near-total/consolidated (effectively
#                                   fast) ice is actually impassable.
# AMSR2 concentration alone can't distinguish thin new ice from thick
# ridged multi-year pack, so treating max_safe_concentration as an
# absolute cutoff for a capable icebreaker was wrong: a Polar Class
# vessel's entire purpose is to operate IN dense pack, just slower and
# at higher risk, not to be routed around it as if it were a wall. The
# weaker classes keep both thresholds equal -- those vessels genuinely
# cannot be in dense pack at all, so no soft zone is appropriate for them.
ICE_CLASS_PROFILES = {
    "not_ice_strengthened": {
        "label": "Not ice-strengthened",
        "max_safe_concentration": 0.15,
        "hard_infeasible_concentration": 0.15,
        "seaice_weight_multiplier": 4.0,
    },
    "ice_strengthened": {
        "label": "Ice-strengthened (non-Polar Class)",
        "max_safe_concentration": 0.50,
        "hard_infeasible_concentration": 0.50,
        "seaice_weight_multiplier": 2.0,
    },
    "polar_class_pc5": {
        "label": "Polar Class PC5",
        "max_safe_concentration": 0.80,
        "hard_infeasible_concentration": 0.98,
        "seaice_weight_multiplier": 1.0,
    },
    "polar_class_pc3_or_higher": {
        "label": "Polar Class PC3 or higher",
        "max_safe_concentration": 0.95,
        "hard_infeasible_concentration": 0.99,
        "seaice_weight_multiplier": 0.5,
    },
}

# How hard the steep escalation past max_safe_concentration bites, relative
# to the base weights (distance=1, seaice up to 3*4=12, iceberg=5) -- large
# enough that the router strongly prefers avoiding this zone when any
# alternative exists, without making it literally infeasible.
STEEP_PENALTY_SCALE = 60.0

CLOSEST_APPROACH_WARNING_KM = 50.0


def _path_distance_km(latlon_path: list) -> float:
    return sum(
        haversine_km(latlon_path[i][0], latlon_path[i][1], latlon_path[i + 1][0], latlon_path[i + 1][1])
        for i in range(len(latlon_path) - 1)
    )


def _path_cost(cost_grid: np.ndarray, index_path: list) -> dict:
    """Sum of cost-grid cells a path crosses, against a SINGLE (day-0)
    grid. Used for the naive route, which isn't feasibility-checked (see
    isochrone.py's naive_route docstring) so it can cross np.inf cells --
    report those separately rather than letting one inf cell make the
    whole score meaningless."""
    finite_sum, infeasible_count = 0.0, 0
    for r, c in index_path:
        v = cost_grid[r, c]
        if np.isfinite(v):
            finite_sum += float(v)
        else:
            infeasible_count += 1
    return {"risk_score": finite_sum, "infeasible_cells_crossed": infeasible_count}


def _path_cost_time_aware(cost_grid_by_day: np.ndarray, latlon_path: list, index_path: list,
                           vessel_speed_kmh: float) -> dict:
    """Same idea as _path_cost(), but scores the isochrone-optimized path
    against whichever day's REAL cost grid applies at the point the ship
    would actually be there (by cumulative distance / speed) -- consistent
    with how isochrone_route() itself picked costs while building the
    path, rather than judging the whole voyage by day-0 conditions."""
    n_days = cost_grid_by_day.shape[0]
    cumulative_km, finite_sum, infeasible_count = 0.0, 0.0, 0
    for i, (r, c) in enumerate(index_path):
        if i > 0:
            cumulative_km += haversine_km(*latlon_path[i - 1], *latlon_path[i])
        day_idx = min(int(cumulative_km / vessel_speed_kmh // 24), n_days - 1)
        v = cost_grid_by_day[day_idx, r, c]
        if np.isfinite(v):
            finite_sum += float(v)
        else:
            infeasible_count += 1
    return {"risk_score": finite_sum, "infeasible_cells_crossed": infeasible_count}


def _day_by_day(optimized_latlon: list, vessel_speed_kmh: float, departure_dt: pd.Timestamp,
                 seaice_forecast: np.ndarray, wind_u_grid, wind_v_grid, current_u_grid, current_v_grid,
                 seaice_is_real: bool, forcing_is_real: bool, seaice_is_true_forecast: bool = False,
                 seaice_mae_by_lead_day: dict = None,
                 horizon_days: int = GRID.forecast_horizon_days) -> list:
    """Bucket the route into forecast days by cumulative distance / speed,
    sampling REAL (where available -- see get_seaice_concentration()/
    get_forcing_fields()) sea-ice concentration and wind/current at each
    point's grid cell AND forecast day (wind/current now vary day to day,
    not a single constant). Points beyond the forecast horizon are
    flagged, not silently dropped -- routing still happened, but there's
    no conditions data that far out yet."""
    n_forcing_days = wind_u_grid.shape[0]
    n_seaice_days = seaice_forecast.shape[0]
    cumulative_km = 0.0
    buckets = {d: {"conc": [], "wind_u": [], "wind_v": [], "current_u": [], "current_v": []}
               for d in range(horizon_days + 1)}
    beyond_horizon_km = None

    for i, (lat, lon) in enumerate(optimized_latlon):
        if i > 0:
            cumulative_km += haversine_km(*optimized_latlon[i - 1], lat, lon)
        day = int(cumulative_km / vessel_speed_kmh // 24)
        if day > horizon_days:
            if beyond_horizon_km is None:
                beyond_horizon_km = cumulative_km
            continue
        row, col = latlon_to_index(lat, lon)
        day_idx = min(day, n_forcing_days - 1)
        seaice_day_idx = min(day, n_seaice_days - 1)
        buckets[day]["conc"].append(float(seaice_forecast[seaice_day_idx, row, col]))
        buckets[day]["wind_u"].append(float(wind_u_grid[day_idx, row, col]))
        buckets[day]["wind_v"].append(float(wind_v_grid[day_idx, row, col]))
        buckets[day]["current_u"].append(float(current_u_grid[day_idx, row, col]))
        buckets[day]["current_v"].append(float(current_v_grid[day_idx, row, col]))

    out = []
    for day in range(horizon_days + 1):
        b = buckets[day]
        has_points = bool(b["conc"])
        out.append({
            "day": day,
            "date": (departure_dt + pd.Timedelta(days=day)).strftime("%Y-%m-%d"),
            "n_route_points": len(b["conc"]),
            "mean_seaice_concentration": float(np.mean(b["conc"])) if has_points else None,
            "max_seaice_concentration": float(np.max(b["conc"])) if has_points else None,
            "wind_u_ms": float(np.mean(b["wind_u"])) if has_points else None,
            "wind_v_ms": float(np.mean(b["wind_v"])) if has_points else None,
            "current_u_ms": float(np.mean(b["current_u"])) if has_points else None,
            "current_v_ms": float(np.mean(b["current_v"])) if has_points else None,
            "seaice_is_real_data": seaice_is_real,
            "seaice_is_true_forecast": seaice_is_true_forecast,
            # Real measured autoregressive MAE for THIS specific lead day
            # (see src/models/seaice_forecast/evaluate_multiday.py) -- day
            # 0 is the real observation itself (no model prediction, so no
            # forecast error applies); later days carry their own real,
            # increasing error rather than one blanket confidence claim.
            "seaice_mae_this_lead_day": (
                None if day == 0 or not seaice_mae_by_lead_day
                else seaice_mae_by_lead_day.get(str(day))
            ),
            "forcing_is_real_data": forcing_is_real,
            "is_placeholder": not (seaice_is_real and forcing_is_real),
        })
    if beyond_horizon_km is not None:
        out.append({
            "day": horizon_days + 1, "date": None,
            "note": f"Route continues {cumulative_km - beyond_horizon_km:.0f} km beyond the "
                    f"{horizon_days}-day forecast horizon — no sea-ice/weather data for that segment yet.",
            "is_placeholder": True,
        })
    return out


def _iceberg_report(iceberg_cluster: list, tracks: dict, optimized_latlon: list,
                     vessel_speed_kmh: float, horizon_days: int = GRID.forecast_horizon_days) -> list:
    """For each tracked iceberg, find the closest approach between the
    ship's day-by-day position along the route and that iceberg's
    predicted position on the same day (not just distance-to-current-
    position, which would ignore that both the ship and the berg move)."""
    cumulative_km = np.array([
        sum(haversine_km(*optimized_latlon[j], *optimized_latlon[j + 1]) for j in range(i))
        for i in range(len(optimized_latlon))
    ])
    ship_day = np.clip((cumulative_km / vessel_speed_kmh // 24).astype(int), 0, horizon_days)

    report = []
    for entry in iceberg_cluster:
        iceberg_id, state = entry["id"], entry["state"]
        member_tracks = tracks.get(iceberg_id, [])
        if not member_tracks:
            continue
        center_track = member_tracks[0]  # [(lat,lon) for day 0..horizon_days]

        best_km, best_day = float("inf"), None
        for day in range(min(horizon_days + 1, len(center_track))):
            ship_points_this_day = [optimized_latlon[i] for i in range(len(optimized_latlon)) if ship_day[i] == day]
            if not ship_points_this_day:
                continue
            iceberg_lat, iceberg_lon = center_track[day]
            for ship_lat, ship_lon in ship_points_this_day:
                d = haversine_km(ship_lat, ship_lon, iceberg_lat, iceberg_lon)
                if d < best_km:
                    best_km, best_day = d, day

        final_positions = [track[-1] for track in member_tracks]
        cone_center = center_track[-1]
        uncertainty_radius_km = max(
            (haversine_km(*cone_center, lat, lon) for lat, lon in final_positions), default=0.0
        )

        report.append({
            "iceberg_id": iceberg_id,
            "current_position": {"lat": state.lat, "lon": state.lon},
            "length_m": state.length_m, "width_m": state.width_m,
            "thickness_m": state.thickness_m, "is_placeholder_thickness": True,
            "predicted_track": [{"day": d, "lat": lat, "lon": lon} for d, (lat, lon) in enumerate(center_track)],
            "drift_uncertainty_radius_km_day7": round(uncertainty_radius_km, 1),
            "closest_approach_km": None if best_day is None else round(best_km, 1),
            "closest_approach_day": best_day,
            "warning": best_day is not None and best_km < CLOSEST_APPROACH_WARNING_KM,
        })
    return report


def plan_journey(start: dict, goal: dict, departure_time: str, vessel_speed_kmh: float, ice_class: str) -> dict:
    """
    start, goal: {"lat": float, "lon": float}
    departure_time: ISO date/datetime string
    vessel_speed_kmh: cruising speed
    ice_class: one of ICE_CLASS_PROFILES' keys
    """
    if ice_class not in ICE_CLASS_PROFILES:
        raise ValueError(f"Unknown ice_class '{ice_class}' — choose one of {list(ICE_CLASS_PROFILES)}")
    if vessel_speed_kmh <= 0:
        raise ValueError("vessel_speed_kmh must be positive")
    profile = ICE_CLASS_PROFILES[ice_class]

    iceberg_cluster = load_iceberg_cluster()
    tracks, source_info = run_drift_ensemble(iceberg_cluster)

    if not BATHY_TIF.exists():
        raise FileNotFoundError(f"{BATHY_TIF} not found — run src/data/download_bathymetry.py first.")
    bathymetry = regrid_bathymetry(BATHY_TIF)

    # Reuse the exact same real (or disclosed-fallback) data run_drift_ensemble
    # already fetched, rather than calling get_seaice_concentration()/
    # get_forcing_fields() a second time.
    seaice_forecast, seaice_info = get_seaice_concentration()  # (n_days, n_lat, n_lon)
    wind_u_grid, wind_v_grid, current_u_grid, current_v_grid, forcing_info = get_forcing_fields()
    horizon_days = seaice_forecast.shape[0] - 1
    iceberg_risk_per_day = rasterize_iceberg_risk_per_day(tracks, horizon_days)  # real per-day drift trajectory risk

    weights = {"distance": 1.0, "seaice": 3.0 * profile["seaice_weight_multiplier"], "iceberg": 5.0}
    cost_grid_by_day = build_cost_grid_stack(seaice_forecast, iceberg_risk_per_day, bathymetry, weights=weights)
    # Beyond max_safe_concentration: steep (quadratic) cost escalation, not
    # yet infeasibility -- a capable icebreaker CAN transit dense pack,
    # just slower and at higher risk, which is the whole point of an ice
    # class rating (see ICE_CLASS_PROFILES docstring above). Applied per
    # day, since a vessel that can't survive today's ice might be fine
    # crossing that same cell on a day the real forecast shows it's
    # cleared, or vice versa.
    max_safe = profile["max_safe_concentration"]
    over_soft = np.clip(seaice_forecast - max_safe, 0.0, None)
    steep_penalty = (over_soft / max(1e-6, 1.0 - max_safe)) ** 2 * STEEP_PENALTY_SCALE
    cost_grid_by_day = cost_grid_by_day + steep_penalty
    # Only true near-total/consolidated (effectively fast) ice is an
    # absolute wall.
    cost_grid_by_day = np.where(
        seaice_forecast > profile["hard_infeasible_concentration"], np.inf, cost_grid_by_day
    )

    start_idx = find_open_water(bathymetry, start["lat"], start["lon"])
    goal_idx = find_open_water(bathymetry, goal["lat"], goal["lon"])

    routing_method = "isochrone"
    try:
        optimized_idx_path, _arrival_hours = isochrone_route(
            cost_grid_by_day, bathymetry, start_idx, goal_idx,
            vessel_speed_kmh=vessel_speed_kmh, resolution_km=RESOLUTION_KM,
        )
    except ValueError as isochrone_err:
        # Real fallback, not a silent one -- disclosed in the response via
        # `routing_method` below. A* only sees day-0 conditions, so this is
        # a real accuracy tradeoff, not equivalent to the isochrone result.
        routing_method = "astar_fallback"
        try:
            optimized_idx_path = astar_route(cost_grid_by_day[0], start_idx, goal_idx)
        except ValueError as e:
            hard = profile["hard_infeasible_concentration"]
            if hard > profile["max_safe_concentration"]:
                limit_desc = f"even this vessel's hard operating limit ({hard*100:.0f}% concentration, effectively consolidated/fast ice)"
            else:
                limit_desc = f"this vessel's safe operating concentration ({hard*100:.0f}%)"
            raise ValueError(
                f"No feasible route found for a '{profile['label']}' vessel between these points — "
                f"the ice/iceberg conditions along every path exceed {limit_desc}. Try a higher ice class "
                f"or a different start/destination. (isochrone: {isochrone_err}; astar: {e})"
            )
    naive_idx_path = naive_route(start_idx, goal_idx)

    optimized_latlon = [index_to_latlon(r, c) for r, c in optimized_idx_path]
    naive_latlon = [index_to_latlon(r, c) for r, c in naive_idx_path]

    # _path_cost() below still wants a single 2-D grid for the naive route's
    # (unconstrained, may cross days) risk scoring -- day-0 is the same
    # representative simplification used before isochrone existed.
    cost_grid = cost_grid_by_day[0]

    optimized_km = _path_distance_km(optimized_latlon)
    naive_km = _path_distance_km(naive_latlon)
    optimized_cost = _path_cost_time_aware(cost_grid_by_day, optimized_latlon, optimized_idx_path, vessel_speed_kmh)
    naive_cost = _path_cost(cost_grid, naive_idx_path)

    departure_dt = pd.Timestamp(departure_time)
    optimized_eta = departure_dt + pd.Timedelta(hours=optimized_km / vessel_speed_kmh)
    naive_eta = departure_dt + pd.Timedelta(hours=naive_km / vessel_speed_kmh)

    risk_reduction_pct = None
    if optimized_cost["risk_score"] > 0 and naive_cost["infeasible_cells_crossed"] == 0:
        risk_reduction_pct = round(
            100 * (naive_cost["risk_score"] - optimized_cost["risk_score"]) / naive_cost["risk_score"], 1
        )

    return {
        "query": {
            "start": start, "goal": goal, "departure_time": departure_dt.isoformat(),
            "vessel_speed_kmh": vessel_speed_kmh, "ice_class": ice_class,
        },
        "ice_class_profile": profile,
        "route_comparison": {
            "optimized": {
                "path": [{"lat": lat, "lon": lon} for lat, lon in optimized_latlon],
                "distance_km": round(optimized_km, 1),
                "eta": optimized_eta.isoformat(),
                "risk_score": round(optimized_cost["risk_score"], 2),
                "routing_method": routing_method,
                "routing_method_note": (
                    "Isochrone: real time-stepped wavefront using the actual day-specific "
                    "sea-ice/iceberg-risk forecast for whichever day the ship would be at each "
                    "point, not one static snapshot for the whole voyage."
                    if routing_method == "isochrone" else
                    "A* fallback: isochrone search found no feasible path, so this route was "
                    "planned against day-0 conditions only for the entire voyage -- less accurate "
                    "for a long voyage than the isochrone method."
                ),
            },
            "naive": {
                "path": [{"lat": lat, "lon": lon} for lat, lon in naive_latlon],
                "distance_km": round(naive_km, 1),
                "eta": naive_eta.isoformat(),
                "risk_score": round(naive_cost["risk_score"], 2),
                "infeasible_cells_crossed": naive_cost["infeasible_cells_crossed"],
            },
            "risk_reduction_pct": risk_reduction_pct,
        },
        "day_by_day": _day_by_day(optimized_latlon, vessel_speed_kmh, departure_dt,
                                   seaice_forecast, wind_u_grid, wind_v_grid, current_u_grid, current_v_grid,
                                   seaice_is_real=seaice_info["is_real_data"],
                                   forcing_is_real=forcing_info["is_real_data"],
                                   seaice_is_true_forecast=seaice_info.get("is_true_forecast", False),
                                   seaice_mae_by_lead_day=seaice_info.get("mae_by_lead_day")),
        "icebergs": _iceberg_report(iceberg_cluster, tracks, optimized_latlon, vessel_speed_kmh),
        "disclosure": {
            "data_sources": {"sea_ice_concentration": seaice_info, "wind_and_current": forcing_info},
            "iceberg_thickness_note": "Estimated from WDE17's published size-class table (see "
                                       "src/integration/pipeline.py's estimate_thickness_m), not measured "
                                       "for these specific icebergs -- see each iceberg's thickness_m.",
            "ice_class_table_note": "Simplified stand-in, not an IACS Polar Class regulatory table.",
        },
    }

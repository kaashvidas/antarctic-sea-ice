"""
Iceberg drift physics (src/models/iceberg_drift/wagner_model.py) --
verifies the real WDE17 port against known-reference distances and
physically-expected regime behavior, not just "does it run."
"""

import math

from src.models.iceberg_drift.wagner_model import (
    IcebergState, step, haversine_km, validate_against_a23a,
    free_drift_force_balance, FREE_DRIFT_THRESHOLD, LOCKED_THRESHOLD,
)


def test_haversine_matches_known_reference_distance():
    # 1 degree of longitude at the equator is ~111.2 km -- a standard,
    # independently-verifiable reference value, not derived from this code.
    d = haversine_km(0, 0, 0, 1)
    assert 110.5 < d < 112.0


def test_haversine_zero_distance():
    assert haversine_km(-60.0, -45.0, -60.0, -45.0) == 0.0


def test_giant_iceberg_is_wind_insensitive():
    """Physical regression check: a huge tabular berg (real D33A scale,
    ~35km long) should be dominated by ocean current, not wind -- this is
    documented real-world behavior for Antarctic tabular icebergs, and is
    what the WDE17 alpha/beta scaling should produce as La -> 0."""
    giant = IcebergState(lat=-64.0, lon=-55.59, length_m=35188, width_m=18520, thickness_m=300)
    small = IcebergState(lat=-64.0, lon=-55.59, length_m=200, width_m=100, thickness_m=50)

    wind_uv = (15.0, 0.0)  # strong wind, no current, isolates wind's contribution
    current_uv = (0.0, 0.0)

    giant_u, giant_v = free_drift_force_balance(giant, *wind_uv, *current_uv)
    small_u, small_v = free_drift_force_balance(small, *wind_uv, *current_uv)

    giant_speed = math.hypot(giant_u, giant_v)
    small_speed = math.hypot(small_u, small_v)
    assert giant_speed < small_speed, (
        f"giant berg drift speed ({giant_speed:.4f} m/s) should be much smaller than a small "
        f"berg's ({small_speed:.4f} m/s) under the same wind, per WDE17's size-scaling"
    )


def test_sea_ice_locking_thresholds():
    """Concentration >= LOCKED_THRESHOLD should move the iceberg exactly
    with the sea-ice velocity, not its own free-drift velocity."""
    from src.models.iceberg_drift.wagner_model import sea_ice_coupled_velocity

    state = IcebergState(lat=-60, lon=-45, length_m=1000, width_m=500, thickness_m=200)
    free_drift = (1.0, 1.0)
    seaice_uv = (0.05, -0.05)

    locked = sea_ice_coupled_velocity(state, free_drift, seaice_uv, LOCKED_THRESHOLD)
    assert locked == seaice_uv

    free = sea_ice_coupled_velocity(state, free_drift, seaice_uv, FREE_DRIFT_THRESHOLD - 0.01)
    assert free == free_drift


def test_step_advects_position():
    """A non-zero velocity should actually move the iceberg -- catches a
    silent no-op in the lat/lon advection math."""
    state = IcebergState(lat=-60.0, lon=-45.0, length_m=1000, width_m=500, thickness_m=200)
    new_state = step(
        state, dt_seconds=24 * 3600,
        wind_uv=(10.0, 5.0), current_uv=(0.1, 0.05),
        seaice_uv=(0.0, 0.0), seaice_concentration=0.0,
    )
    assert (new_state.lat, new_state.lon) != (state.lat, state.lon)
    # A giant/small berg moving under real-scale forcing over 1 day should
    # cover a physically plausible distance (not thousands of km, not zero).
    moved_km = haversine_km(state.lat, state.lon, new_state.lat, new_state.lon)
    assert 0.0 < moved_km < 200.0


def test_validate_against_a23a_haversine_error():
    predicted = [(-60.0, -45.0), (-60.1, -45.1)]
    observed = [(-60.0, -45.0), (-60.0, -45.0)]
    result = validate_against_a23a(predicted, observed)
    assert result["errors_km"][0] == 0.0
    assert result["errors_km"][1] > 0.0
    assert result["mean_km"] == sum(result["errors_km"]) / 2

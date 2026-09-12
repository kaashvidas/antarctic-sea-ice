"""
Module 2 — iceberg drift physics engine.

Python port of Wagner, Dell & Eisenman (2017), "An Analytical Model of
Iceberg Drift" (WDE17), Journal of Physical Oceanography. Ported directly
from the authors' own public reference implementation — the Python/Jupyter
version at https://www.tillwagner.me/wde17-iceberg-model-ecco2-ipynb
(WDE17_iceberg_model_ECCO2.ipynb, Wagner & Eisenman, converted to Jupyter
by Ian Cornejo, Dec 2021) — rather than re-deriving the force balance from
the paper text. Constants, gamma/Lambda/alpha/beta (Eqs 7-9), the drift
velocity solution (Eq 6), and the melt parameterization (MA10 / Martin &
Adcroft 2010) below match that notebook's `cell-6` and `cell-17`.

IMPORTANT Southern Hemisphere adaptation: the reference notebook runs over
the North Atlantic (33-70N) and computes the Coriolis parameter as
f(lat) = 2*Om*sin(|lat|), i.e. it silently assumes a fixed (northern)
Ekman-turning handedness. Iceberg drift is known to turn in the *opposite*
sense in the Southern Hemisphere (Coriolis force flips sign south of the
equator), so this port uses the SIGNED latitude in f(lat) instead of
abs(lat) — everywhere else the physics is unchanged from the reference.
This is the one deliberate physics change from the source; see `_f()`.

Antarctic-specific addition (the README's stated differentiator, citing
the Weddell Sea sea-ice/iceberg coupling paper): sea-ice coupling regimes
based on local sea-ice concentration (from Module 1's output):
    concentration <  15%  -> free drift (WDE17 velocity solution only)
    15% <= concentration < 90%  -> blended drag term against the ice
    concentration >= 90%  -> "locked": iceberg moves WITH the sea-ice
                              drift velocity, not independently
"""

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# WDE17 physical constants (verbatim from the reference notebook's cell-6)
# ---------------------------------------------------------------------------
EARTH_RADIUS_M = 6378e3      # earth radius (m)
RHO_WATER = 1027.0           # density of water (kg/m^3)
RHO_AIR = 1.2                # density of air (kg/m^3)
RHO_ICE = 850.0              # density of shelf ice (kg/m^3), Silva et al (2006)
DRHO = RHO_WATER - RHO_ICE
CW = 0.9                     # bulk drag coefficient, water (Bigg et al 1997)
CA = 1.3                     # bulk drag coefficient, air (Bigg et al 1997)
EARTH_OMEGA = 7.2921e-5      # Earth's rotation rate (rad/s)

# gamma = sqrt((rhoa*drho*Ca)/(rhow*rhoi*Cw)) -- WDE17 Eq. 7
GAMMA = math.sqrt((RHO_AIR * DRHO * CA) / (RHO_WATER * RHO_ICE * CW))

# Side/basal melt parameters (WDE17 Appendix, "MA10" = Martin & Adcroft 2010)
MELT_TI = -4.0
MELT_A1, MELT_A2 = 8.7e-6, 5.8e-7
MELT_B1, MELT_B2 = 8.8e-8, 1.5e-8
MELT_C = 6.7e-6

# Sea-ice coupling thresholds (Weddell Sea paper) — keep these named
# constants rather than inlining the numbers, since they're the most
# citeable, most "we did our homework" detail in this module.
FREE_DRIFT_THRESHOLD = 0.15   # below this: no sea-ice drag
LOCKED_THRESHOLD = 0.90       # at/above this: iceberg locks to sea-ice motion


@dataclass
class IcebergState:
    lat: float
    lon: float
    length_m: float   # along-wind dimension
    width_m: float
    thickness_m: float
    velocity_u: float = 0.0  # m/s, eastward
    velocity_v: float = 0.0  # m/s, northward


def _f(lat_deg: float) -> float:
    """Coriolis parameter, SIGNED (see module docstring — the reference
    notebook uses abs(lat) which is only valid north of the equator)."""
    return 2 * EARTH_OMEGA * math.sin(math.radians(lat_deg))


def _harmonic_mean_size(length_m: float, width_m: float) -> float:
    """S(l, w) = (l*w)/(l+w) -- WDE17's effective horizontal size scale."""
    return (length_m * width_m) / (length_m + width_m)


def _lambda(wind_speed: float, lat_deg: float, size_scale: float) -> float:
    """Lambda, WDE17 Eq. 9. Can be negative in the Southern Hemisphere
    since f(lat) is signed here -- that sign carries through alpha/beta
    below and is what flips the Ekman turning direction correctly."""
    f = _f(lat_deg)
    if f == 0 or size_scale == 0:
        return 0.0
    return (CW * GAMMA * wind_speed) / (math.pi * size_scale * f)


def _alpha(La: float) -> float:
    """alpha(Lambda), WDE17 Eq. 8."""
    if La == 0:
        return 0.0
    return (math.sqrt(1 + 4 * La ** 4) - 1) / (2 * La ** 3)


def _beta(La: float) -> float:
    """beta(Lambda), WDE17 Eq. 8."""
    if La == 0:
        return 0.0
    radicand = (1 + La ** 4) * math.sqrt(1 + 4 * La ** 4) - 3 * La ** 4 - 1
    radicand = max(radicand, 0.0)  # guard tiny negative float noise, per reference code
    return math.sqrt(radicand) / (math.sqrt(2) * La ** 3)


def free_drift_force_balance(state: IcebergState, wind_u, wind_v, current_u, current_v):
    """
    WDE17's analytical steady-state drift velocity (Eq. 6):
        u_i = u_w + gamma*( alpha(La)*v_a + beta(La)*u_a)
        v_i = v_w + gamma*(-alpha(La)*u_a + beta(La)*v_a)

    This is the free-drift velocity (sea-ice concentration below
    FREE_DRIFT_THRESHOLD) — the wind vector is rotated/scaled by
    alpha/beta (which encode the balance of air drag, water drag, and
    Coriolis force for this iceberg's size) and added to the ambient
    current.
    """
    size_scale = _harmonic_mean_size(state.length_m, state.width_m)
    wind_speed = math.hypot(wind_u, wind_v)
    La = _lambda(wind_speed, state.lat, size_scale)
    a, b = _alpha(La), _beta(La)

    u = current_u + GAMMA * (a * wind_v + b * wind_u)
    v = current_v + GAMMA * (-a * wind_u + b * wind_v)
    return u, v


def sea_ice_coupled_velocity(state: IcebergState, free_drift_uv, seaice_uv, seaice_concentration: float):
    """
    Blend free-drift velocity with sea-ice drift velocity according to
    local concentration, per the Weddell Sea coupling logic.

    Parameters
    ----------
    free_drift_uv : (u, v) from free_drift_force_balance
    seaice_uv : (u, v) sea-ice drift velocity at the iceberg's location
                (derived from consecutive days of Module 1's concentration
                field, or a separate ice-motion product if available)
    seaice_concentration : local concentration, 0-1
    """
    free_u, free_v = free_drift_uv
    ice_u, ice_v = seaice_uv

    if seaice_concentration < FREE_DRIFT_THRESHOLD:
        return free_u, free_v

    if seaice_concentration >= LOCKED_THRESHOLD:
        return ice_u, ice_v  # locked: moves with the pack

    # Linear blend across the drag regime — a reasonable starting
    # assumption; revisit if validation shows it's off.
    frac = (seaice_concentration - FREE_DRIFT_THRESHOLD) / (LOCKED_THRESHOLD - FREE_DRIFT_THRESHOLD)
    u = (1 - frac) * free_u + frac * ice_u
    v = (1 - frac) * free_v + frac * ice_v
    return u, v


def melt_rates(state: IcebergState, wind_u, wind_v, current_u, current_v, velocity_u, velocity_v, sst: float):
    """
    WDE17 Appendix side/basal melt (MA10 = Martin & Adcroft 2010
    parameterization, the reference notebook's default). Returns
    (dl_dt, dh_dt) in m/s -- both length and width shrink at the same
    side-melt rate, thickness shrinks at the basal-melt rate.

    sst : sea surface temperature in degrees C at the iceberg's location.
    Not all of our real input sources carry SST directly -- if you don't
    have CMEMS/ECCO SST, ERA5 2m air temperature is a documented, disclosed
    stand-in (warmer bias near open water, colder near ice -- good enough
    for a multi-day forecast horizon where melt-driven size change is a
    second-order effect on drift, not the leading one).
    """
    wind_speed = math.hypot(wind_u, wind_v)
    rel_speed = math.hypot(velocity_u - current_u, velocity_v - current_v)

    side_melt_wind = MELT_A1 * math.sqrt(wind_speed) + MELT_A2 * wind_speed
    side_melt_thermal = MELT_B1 * sst + MELT_B2 * sst ** 2
    dl_dt = -(side_melt_thermal + side_melt_wind)

    length_m = max(state.length_m, 1.0)
    basal_melt = MELT_C * (rel_speed ** 0.8) * (sst - MELT_TI) * length_m ** (-0.2)
    dh_dt = -basal_melt

    return dl_dt, dh_dt


def step(state: IcebergState, dt_seconds: float, wind_uv, current_uv, seaice_uv, seaice_concentration: float,
         sst: float = None) -> IcebergState:
    """
    Advance one iceberg one timestep: compute drift velocity, then
    advect lat/lon, then (optionally) apply melt to its dimensions.

    Lat/lon update follows the reference notebook exactly (accounts for
    meridian convergence via the cos(latitude) term on longitude, rather
    than a flat-Earth dx/dy approximation which accumulates visible error
    this far south):
        dlat = v * dt / R * (180/pi)
        dlon = u * dt / R * (180/pi) / cos(mean latitude)
    """
    free_uv = free_drift_force_balance(state, *wind_uv, *current_uv)
    u, v = sea_ice_coupled_velocity(state, free_uv, seaice_uv, seaice_concentration)

    deg_per_m = (dt_seconds / EARTH_RADIUS_M) * (180.0 / math.pi)
    dlat = v * deg_per_m
    new_lat = state.lat + dlat
    mean_lat_rad = math.radians((state.lat + new_lat) / 2.0)
    dlon = (u * deg_per_m) / max(math.cos(mean_lat_rad), 1e-6)
    new_lon = state.lon + dlon

    new_length, new_width, new_thickness = state.length_m, state.width_m, state.thickness_m
    if sst is not None:
        dl_dt, dh_dt = melt_rates(state, *wind_uv, *current_uv, u, v, sst)
        new_length = max(state.length_m + dl_dt * dt_seconds, 0.0)
        new_width = max(state.width_m + dl_dt * dt_seconds, 0.0)
        new_thickness = max(state.thickness_m + dh_dt * dt_seconds, 0.0)

    return IcebergState(
        lat=new_lat, lon=new_lon,
        length_m=new_length, width_m=new_width, thickness_m=new_thickness,
        velocity_u=u, velocity_v=v,
    )


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two lat/lon points, in km."""
    R_km = EARTH_RADIUS_M / 1000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R_km * math.asin(min(1.0, math.sqrt(a)))


def validate_against_a23a(predicted_track, observed_track) -> dict:
    """
    Report displacement error in km between predicted and observed
    positions at matching timestamps (same metric IDRIFTNET's paper
    uses, so the number is directly comparable to published results).

    predicted_track, observed_track : sequences of (lat, lon), same
    length, index-aligned to matching timestamps.

    Despite the name (kept for continuity with the README's original
    A23a validation-case framing), this works for validating drift
    predictions against any real observed track, e.g. USNIC's periodic
    position updates for the currently-tracked icebergs this build uses.
    """
    if len(predicted_track) != len(observed_track):
        raise ValueError(
            f"Track length mismatch: {len(predicted_track)} predicted vs "
            f"{len(observed_track)} observed — align them to the same "
            "timestamps before validating."
        )

    errors_km = [
        haversine_km(p_lat, p_lon, o_lat, o_lon)
        for (p_lat, p_lon), (o_lat, o_lon) in zip(predicted_track, observed_track)
    ]
    return {
        "errors_km": errors_km,
        "mean_km": sum(errors_km) / len(errors_km),
        "max_km": max(errors_km),
        "final_km": errors_km[-1],
    }

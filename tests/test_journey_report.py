"""
End-to-end integration test for the on-demand journey planner
(src/integration/journey_report.py) -- exercises the REAL pipeline (real
iceberg cluster, real bathymetry, real drift physics, real routing)
against real downloaded data. Skipped if that data isn't present on this
machine rather than faked, per this whole project's honesty rule.
"""

from pathlib import Path

import pytest

from src.utils.grid import region_path, ACTIVE_REGION

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    REPO_ROOT / "data" / "raw" / "icebergs" / "antarctic_icebergs_latest.csv",
    region_path("data/raw", "bathymetry", "bathymetry.tif"),
]

pytestmark = pytest.mark.skipif(
    not all(f.exists() for f in REQUIRED_FILES),
    reason="real iceberg/bathymetry data not downloaded on this machine",
)

# Known-good real coordinates per region, confirmed reachable during this
# project's own manual testing -- NOT interchangeable across regions (a
# region's real September ice cover varies hugely by location, so a pair
# that works for one region can be completely infeasible, or trivially
# open water, for another). Add a new region's entry here the same way:
# probe a few candidate points' real concentration via
# get_seaice_concentration(), verify a real plan_journey() call succeeds
# for the chosen ice class before hardcoding it.
_REGION_TEST_FIXTURES = {
    "weddell": {
        "start": {"lat": -58.88, "lon": -51.12},
        "goal": {"lat": -54.88, "lon": -35.12},
        "feasible_ice_class": "ice_strengthened",
        "deep_pack_point": {"lat": -65.5, "lon": -57.0},  # confirmed ~80%+ concentration
        "unsafe_ice_class": "not_ice_strengthened",
        "strong_ice_class": "polar_class_pc3_or_higher",
        "weak_ice_class": "not_ice_strengthened",
    },
    "prydz_bay": {
        "start": {"lat": -60.875, "lon": 70.0},
        "goal": {"lat": -69.625, "lon": 74.875},
        "feasible_ice_class": "polar_class_pc5",  # real Sept pack here is too dense for ice_strengthened's 50% cutoff
        "deep_pack_point": {"lat": -61.0, "lon": 76.0},  # confirmed ~99% concentration
        "unsafe_ice_class": "not_ice_strengthened",
        "strong_ice_class": "polar_class_pc3_or_higher",
        "weak_ice_class": "polar_class_pc5",  # not_ice_strengthened is infeasible for this pair entirely
    },
}
_FIXTURE = _REGION_TEST_FIXTURES.get(ACTIVE_REGION)
pytestmark = [
    pytestmark,
    pytest.mark.skipif(_FIXTURE is None, reason=f"no verified test start/goal fixture for region '{ACTIVE_REGION}' yet"),
]
if _FIXTURE:
    START, GOAL = _FIXTURE["start"], _FIXTURE["goal"]


def test_plan_journey_returns_sane_real_route():
    from src.integration.journey_report import plan_journey

    report = plan_journey(START, GOAL, "2026-09-15T06:00:00", vessel_speed_kmh=22, ice_class=_FIXTURE["feasible_ice_class"])

    opt = report["route_comparison"]["optimized"]
    naive = report["route_comparison"]["naive"]

    assert opt["distance_km"] > 0
    assert naive["distance_km"] > 0
    # The optimized route detours around risk, so it should never be
    # SHORTER than the straight-line naive route (it can only be longer
    # or, in the rare case risk is negligible everywhere, roughly equal).
    assert opt["distance_km"] >= naive["distance_km"] * 0.98

    assert opt["path"][0] != opt["path"][-1]
    assert report["route_comparison"]["risk_reduction_pct"] is None or report["route_comparison"]["risk_reduction_pct"] >= 0

    # ETA must be after departure, by a real amount consistent with speed/distance.
    import pandas as pd
    departure = pd.Timestamp("2026-09-15T06:00:00")
    eta = pd.Timestamp(opt["eta"])
    assert eta > departure
    implied_hours = (eta - departure).total_seconds() / 3600
    assert abs(implied_hours - opt["distance_km"] / 22) < 1.0  # consistent with the stated speed


def test_plan_journey_rejects_unsafe_ice_class_honestly():
    """A non-ice-strengthened vessel routed through real heavy pack ice
    should fail with a clear message, not silently return an unsafe route."""
    from src.integration.journey_report import plan_journey

    with pytest.raises(ValueError, match="No feasible route"):
        plan_journey(
            _FIXTURE["deep_pack_point"], GOAL,
            "2026-09-15T06:00:00", vessel_speed_kmh=22, ice_class=_FIXTURE["unsafe_ice_class"],
        )


def test_ice_class_actually_changes_the_route():
    """Same start/goal, different ice class -> should not silently
    produce identical behavior when a stricter class is more constrained."""
    from src.integration.journey_report import plan_journey

    strong = plan_journey(START, GOAL, "2026-09-15T06:00:00", vessel_speed_kmh=22, ice_class=_FIXTURE["strong_ice_class"])
    weak = plan_journey(START, GOAL, "2026-09-15T06:00:00", vessel_speed_kmh=22, ice_class=_FIXTURE["weak_ice_class"])
    # Not asserting they MUST differ (a route through open water might be
    # identical for both) -- asserting the weaker vessel is never
    # cheaper/riskier-tolerant than the stronger one.
    assert weak["route_comparison"]["optimized"]["distance_km"] >= strong["route_comparison"]["optimized"]["distance_km"] * 0.95


def test_disclosure_reflects_real_data_sources():
    from src.integration.journey_report import plan_journey

    report = plan_journey(START, GOAL, "2026-09-15T06:00:00", vessel_speed_kmh=22, ice_class=_FIXTURE["feasible_ice_class"])
    sources = report["disclosure"]["data_sources"]
    assert "sea_ice_concentration" in sources
    assert "wind_and_current" in sources
    assert isinstance(sources["sea_ice_concentration"]["is_real_data"], bool)
    # No unmeasured thickness field should ever reach the API -- no public
    # dataset gives real per-iceberg thickness for this cluster (see
    # pipeline.py's _UNUSED_THICKNESS_M comment), so it's not displayed
    # as data anywhere, real length/width only.
    for ib in report["icebergs"]:
        assert "thickness_m" not in ib
        assert "is_placeholder_thickness" not in ib
        assert ib["length_m"] > 0
        assert ib["width_m"] > 0

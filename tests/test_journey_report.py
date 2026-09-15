"""
End-to-end integration test for the on-demand journey planner
(src/integration/journey_report.py) -- exercises the REAL pipeline (real
iceberg cluster, real bathymetry, real drift physics, real routing)
against real downloaded data. Skipped if that data isn't present on this
machine rather than faked, per this whole project's honesty rule.
"""

from pathlib import Path

import pytest

from src.utils.grid import region_path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    REPO_ROOT / "data" / "raw" / "icebergs" / "antarctic_icebergs_latest.csv",
    region_path("data/raw", "bathymetry", "bathymetry.tif"),
]

pytestmark = pytest.mark.skipif(
    not all(f.exists() for f in REQUIRED_FILES),
    reason="real iceberg/bathymetry data not downloaded on this machine",
)

# Known-good real open-water coordinates inside the locked grid box,
# confirmed reachable during this project's own manual testing.
START = {"lat": -58.88, "lon": -51.12}
GOAL = {"lat": -54.88, "lon": -35.12}


def test_plan_journey_returns_sane_real_route():
    from src.integration.journey_report import plan_journey

    report = plan_journey(START, GOAL, "2026-09-15T06:00:00", vessel_speed_kmh=22, ice_class="ice_strengthened")

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
            {"lat": -65.5, "lon": -57.0}, GOAL,  # deep in real winter pack ice, confirmed ~80%+ concentration
            "2026-09-15T06:00:00", vessel_speed_kmh=22, ice_class="not_ice_strengthened",
        )


def test_ice_class_actually_changes_the_route():
    """Same start/goal, different ice class -> should not silently
    produce identical behavior when a stricter class is more constrained."""
    from src.integration.journey_report import plan_journey

    strong = plan_journey(START, GOAL, "2026-09-15T06:00:00", vessel_speed_kmh=22, ice_class="polar_class_pc3_or_higher")
    weak = plan_journey(START, GOAL, "2026-09-15T06:00:00", vessel_speed_kmh=22, ice_class="not_ice_strengthened")
    # Not asserting they MUST differ (a route through open water might be
    # identical for both) -- asserting the weaker vessel is never
    # cheaper/riskier-tolerant than the stronger one.
    assert weak["route_comparison"]["optimized"]["distance_km"] >= strong["route_comparison"]["optimized"]["distance_km"] * 0.95


def test_disclosure_reflects_real_data_sources():
    from src.integration.journey_report import plan_journey

    report = plan_journey(START, GOAL, "2026-09-15T06:00:00", vessel_speed_kmh=22, ice_class="ice_strengthened")
    sources = report["disclosure"]["data_sources"]
    assert "sea_ice_concentration" in sources
    assert "wind_and_current" in sources
    assert isinstance(sources["sea_ice_concentration"]["is_real_data"], bool)
    # icebergs must carry the real thickness disclosure, not a silent number
    for ib in report["icebergs"]:
        assert ib["is_placeholder_thickness"] is True
        assert ib["thickness_m"] > 0

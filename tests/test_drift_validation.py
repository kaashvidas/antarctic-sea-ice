"""
Real drift-model validation against observed iceberg tracks (see
src/models/iceberg_drift/validate_drift.py) -- reports (and sanity-checks)
the actual skill of the live WDE17 step() against real BYU/NIC observed
positions, not a synthetic check. Skipped if the validation hasn't been
run on this machine yet.
"""

import json
from pathlib import Path

import pytest

from src.utils.grid import region_path

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATION_PATH = region_path("data/processed", "drift_validation.json")


@pytest.mark.skipif(not VALIDATION_PATH.exists(), reason="drift validation not run on this machine yet")
def test_real_drift_validation_skill():
    payload = json.loads(VALIDATION_PATH.read_text())
    summary = payload["summary"]

    assert summary["n_icebergs_validated"] >= 1

    print(f"\nReal drift validation ({summary['n_icebergs_validated']} icebergs: "
          f"{', '.join(summary['icebergs'])}) against {payload['ground_truth_source']}:")
    for r in payload["per_iceberg"]:
        print(f"  {r['iceberg_id']}: {r['n_days_validated']}d, mean error {r['mean_error_km']} km "
              f"(persistence baseline {r['mean_baseline_error_km']} km)")

    for r in payload["per_iceberg"]:
        assert r["mean_error_km"] >= 0.0
        # sanity bound: a real tabular berg in this domain does not drift
        # thousands of km in a 20-day validation window
        assert r["mean_error_km"] < 1000.0

    beats_baseline = summary["overall_mean_error_km"] < summary["overall_mean_baseline_error_km"]
    print(f"  Overall: {summary['overall_mean_error_km']} km vs persistence baseline "
          f"{summary['overall_mean_baseline_error_km']} km -- beats baseline: {beats_baseline}")
    # Not asserted as pass/fail at the per-iceberg level (one iceberg,
    # D33B, is real-data-honest and does NOT beat baseline -- see
    # validate_drift.py's docstring) -- but the aggregate across all
    # validated icebergs should show real skill, or this "validation"
    # isn't actually validating anything.
    assert beats_baseline

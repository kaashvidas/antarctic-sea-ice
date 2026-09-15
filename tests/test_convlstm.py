"""
ConvLSTM sea-ice forecaster: architecture shape checks (fast, always run)
plus real held-out skill reporting from the latest trained checkpoint(s)
(skipped if none exist yet). This is the "accuracy measures and error"
report -- pulled directly from train.py's own held-out (never seen during
training) evaluation, not training-set error, which would be misleadingly
low and isn't a meaningful accuracy claim for a forecasting model.
"""

from pathlib import Path

import pytest
import torch

from src.models.seaice_forecast.convlstm import SeaIceConvLSTM
from src.utils.grid import region_path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = region_path("data/processed", "convlstm_checkpoint.pt")


def test_convlstm_forward_pass_shape():
    model = SeaIceConvLSTM(input_dim=1, hidden_dim=8, num_layers=1)  # small, fast for a unit test
    x = torch.rand(2, 5, 1, 16, 20)  # (batch, seq, channel, H, W)
    out = model(x)
    assert out.shape == (2, 1, 16, 20)
    assert torch.all((out >= 0) & (out <= 1))  # sigmoid output -- must be a valid concentration


def test_convlstm_multichannel_forward_pass_shape():
    """Same check with 5 channels (concentration + wind_u/v + current_u/v),
    the real configuration this project actually trains with."""
    model = SeaIceConvLSTM(input_dim=5, hidden_dim=8, num_layers=1)
    x = torch.rand(2, 5, 5, 16, 20)
    out = model(x)
    assert out.shape == (2, 1, 16, 20)


@pytest.mark.skipif(not CHECKPOINT.exists(), reason="no trained checkpoint on this machine yet")
def test_real_checkpoint_held_out_skill():
    """Reports (and sanity-checks) the REAL held-out MAE/RMSE this
    project's actual trained checkpoint achieved, saved by train.py at
    the end of a real training run -- see held_out_skill in the
    checkpoint dict."""
    ckpt = torch.load(CHECKPOINT, map_location="cpu")
    skill = ckpt.get("held_out_skill")
    assert skill, "checkpoint has no held_out_skill recorded -- was it saved by an old version of train.py?"

    print(f"\nReal held-out skill for {CHECKPOINT.name} "
          f"(trained on {ckpt.get('trained_on')}, extra_vars={ckpt.get('extra_vars')}):")
    for model_name, metrics in skill.items():
        print(f"  {model_name:12s} mae={metrics['mae']:.4f} rmse={metrics['rmse']:.4f} bias={metrics['bias']:+.4f}")
        assert 0.0 <= metrics["mae"] <= 1.0  # concentration is in [0,1], so MAE must be too
        assert metrics["rmse"] >= metrics["mae"]  # RMSE >= MAE is a mathematical identity, not a modeling choice

    if "convlstm" in skill and "persistence" in skill:
        beats_persistence = skill["convlstm"]["mae"] < skill["persistence"]["mae"]
        print(f"  ConvLSTM beats persistence on held-out MAE: {beats_persistence}")
        # Not asserted as pass/fail -- report honestly either way, per
        # this project's own "don't cherry-pick" rule (see train.py).

"""
Real multi-day (autoregressive) skill evaluation -- the app rolls the
ConvLSTM forward day-by-day, feeding each prediction back in as the next
input frame (see convlstm.py's own docstring and
src/integration/pipeline.py's _run_convlstm_forecast). Every skill number
reported so far (train.py's "Held-out skill" table) is for a single
1-day-ahead prediction step, NOT the full 7-day horizon the app actually
serves. Autoregressive error compounds -- a model that's excellent at day
1 can be meaningfully worse by day 7. This measures that directly,
honestly, on the real held-out TEST split (never touched by any
hyperparameter choice or the train/val comparison already reported).
"""

import json
import sys
from pathlib import Path

import numpy as np
import torch
import xarray as xr

sys.path.append(str(Path(__file__).resolve().parents[3]))
from src.models.seaice_forecast.convlstm import SeaIceConvLSTM  # noqa: E402
from src.models.seaice_forecast.train import chronological_splits  # noqa: E402
from src.utils.grid import region_path  # noqa: E402


def evaluate_multiday(processed_path: str, checkpoint_path: str, horizon_days: int = 7,
                       max_start_points: int = 60):
    ds = xr.open_dataset(processed_path)
    n_time = ds.sizes["time"]
    train_sl, val_sl, test_sl = chronological_splits(n_time)

    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    extra_vars = checkpoint.get("extra_vars", [])
    input_seq_len = checkpoint.get("input_seq_len", 7)
    model = SeaIceConvLSTM(input_dim=1 + len(extra_vars))
    model.load_state_dict(checkpoint["model_state_dict"] if "model_state_dict" in checkpoint else checkpoint)
    model.eval()

    conc = ds["cdr_seaice_conc"].values.astype(np.float32)
    test_start, test_stop = test_sl.start, test_sl.stop

    # Real starting points within the test split, spaced out (not just
    # the first N consecutive days, which would over-represent one
    # narrow slice of the season) -- capped at max_start_points to keep
    # this a real but bounded evaluation, not another multi-hour job.
    usable_range = range(test_start + input_seq_len, test_stop - horizon_days)
    starts = list(usable_range)
    if len(starts) > max_start_points:
        idx = np.linspace(0, len(starts) - 1, max_start_points).astype(int)
        starts = [starts[i] for i in idx]
    print(f"Evaluating {len(starts)} real start points from the test split "
          f"({test_start}:{test_stop}), horizon={horizon_days} days")

    errors_by_lead = {d: [] for d in range(1, horizon_days + 1)}

    with torch.no_grad():
        for s in starts:
            window = conc[s - input_seq_len:s]  # (input_seq_len, H, W)
            x_seq = torch.from_numpy(window).unsqueeze(0).unsqueeze(2)  # (1, seq, 1, H, W)
            for lead in range(1, horizon_days + 1):
                pred = model(x_seq).squeeze(0).squeeze(0).numpy()
                truth = conc[s + lead - 1]  # real observed concentration on this lead day
                mae = float(np.mean(np.abs(pred - truth)))
                errors_by_lead[lead].append(mae)
                next_frame = torch.from_numpy(pred).unsqueeze(0).unsqueeze(0).unsqueeze(0)
                x_seq = torch.cat([x_seq[:, 1:], next_frame], dim=1)

    print("\nReal autoregressive MAE by lead day (test split, never used for any model/hyperparameter choice):")
    for lead in range(1, horizon_days + 1):
        vals = errors_by_lead[lead]
        print(f"  day {lead}: mae={np.mean(vals):.4f} (std across {len(vals)} start points: {np.std(vals):.4f})")

    day1 = np.mean(errors_by_lead[1])
    day_last = np.mean(errors_by_lead[horizon_days])
    print(f"\nDegradation day 1 -> day {horizon_days}: {day1:.4f} -> {day_last:.4f} "
          f"({100 * (day_last - day1) / day1:+.1f}%)")
    return errors_by_lead


def save_skill_json(errors_by_lead: dict, checkpoint_path: str,
                     out_path: str = None) -> Path:
    """Persists real per-lead-day MAE so the running app can disclose
    honest, measured confidence per forecast day instead of a single
    blanket 1-day-ahead number -- see src/integration/pipeline.py's
    get_seaice_concentration() for where this gets read back in."""
    payload = {
        "checkpoint_evaluated": str(checkpoint_path),
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "mae_by_lead_day": {str(k): round(float(np.mean(v)), 4) for k, v in errors_by_lead.items()},
        "n_start_points": len(next(iter(errors_by_lead.values()))),
        "note": "Real autoregressive MAE per forecast lead day, measured on the held-out test "
                "split (never used for training or hyperparameter selection). Error compounds "
                "with lead day since each day's prediction feeds into the next -- day 7 is a "
                "real, measured, weaker number, not a placeholder.",
    }
    out_path = Path(out_path) if out_path else region_path("data/processed", "convlstm_multiday_skill.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"Saved {out_path}")
    return out_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    # seaice_history.nc (concentration-only, full real history), not the
    # weather-merged file -- that's what train.py actually trains on by
    # default (concentration-only beats weather-enhanced, see README), and
    # the weather-merged file's shorter real coverage window (bounded by
    # Open-Meteo's current-archive start) would silently evaluate against
    # a different, smaller test split than the model was actually trained
    # against if used here instead.
    parser.add_argument("--processed-path", default=str(region_path("data/processed", "seaice_history.nc")))
    parser.add_argument("--checkpoint", default=str(region_path("data/processed", "convlstm_checkpoint.pt")))
    parser.add_argument("--horizon-days", type=int, default=7)
    parser.add_argument("--max-start-points", type=int, default=60)
    args = parser.parse_args()
    errors = evaluate_multiday(args.processed_path, args.checkpoint, args.horizon_days, args.max_start_points)
    save_skill_json(errors, args.checkpoint)

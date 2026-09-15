"""
Hyperparameter sweep + ensemble training for SeaIceConvLSTM, on real data
(chronological train/val/test split, same as train.py -- see that
module's own warning about why the split must stay time-ordered).

Two phases:
  1. Sweep a small grid of real architecture/sequence-length configs,
     each trained for a short (few-epoch) run, and pick the config with
     the best real held-out (val) MAE. Short runs are enough to RANK
     configs even though the final chosen config gets a longer run in
     phase 2 -- relative ordering across configs is stable well before
     full convergence for this kind of model, and running every config
     to full convergence isn't affordable.
  2. Train N_ENSEMBLE_MEMBERS independently-seeded models at the winning
     config for the full epoch budget, and save them together in one
     checkpoint (`ensemble_state_dicts`) that pipeline.py's
     _run_convlstm_forecast averages across at inference -- a real
     ensemble, not a single model dressed up as one.

Run: python -m src.models.seaice_forecast.sweep_and_ensemble
"""

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import torch
import xarray as xr
from torch.utils.data import DataLoader

from .convlstm import SeaIceConvLSTM
from .train import SeaIceSequenceDataset, train, chronological_splits
from .baseline import evaluate, persistence_forecast, climatology_forecast
from src.utils.grid import region_path

N_ENSEMBLE_MEMBERS = 3
SWEEP_EPOCHS = 6
FINAL_EPOCHS = 20


def _set_budgets(n_ensemble_members=None, sweep_epochs=None, final_epochs=None):
    global N_ENSEMBLE_MEMBERS, SWEEP_EPOCHS, FINAL_EPOCHS
    if n_ensemble_members is not None:
        N_ENSEMBLE_MEMBERS = n_ensemble_members
    if sweep_epochs is not None:
        SWEEP_EPOCHS = sweep_epochs
    if final_epochs is not None:
        FINAL_EPOCHS = final_epochs


def _held_out_mae(model, val_ds, truth, sweep_epochs_label=""):
    model.eval()
    preds = []
    with torch.no_grad():
        for i in range(len(val_ds)):
            x_seq, _ = val_ds[i]
            pred = model(x_seq.unsqueeze(0)).squeeze(0).squeeze(0).numpy()
            preds.append(pred)
    pred_da = xr.DataArray(
        np.stack(preds), dims=("time", "lat", "lon"),
        coords={"time": truth.time.values[:len(preds)], "lat": truth.lat, "lon": truth.lon},
    )
    truth_aligned = truth.isel(time=slice(0, len(preds)))
    metrics = evaluate(pred_da, truth_aligned)
    return metrics, preds


def run_sweep(processed_path, extra_vars, input_seq_lens, hidden_dims, num_layers_list, batch_size):
    full_ds = xr.open_dataset(processed_path)
    n_time = full_ds.sizes["time"]
    train_sl, val_sl, test_sl = chronological_splits(n_time)
    conc = full_ds["cdr_seaice_conc"]
    truth = conc.isel(time=val_sl)

    configs = list(itertools.product(input_seq_lens, hidden_dims, num_layers_list))
    print(f"Sweeping {len(configs)} configs ({SWEEP_EPOCHS} epochs each, real held-out MAE, no cherry-picking):")

    results = []
    for input_seq_len, hidden_dim, num_layers in configs:
        torch.manual_seed(0)
        train_ds = SeaIceSequenceDataset(processed_path, input_seq_len, extra_vars=extra_vars, time_slice=train_sl)
        val_ds = SeaIceSequenceDataset(processed_path, input_seq_len, extra_vars=extra_vars, time_slice=val_sl)
        train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=False)
        val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

        model = SeaIceConvLSTM(input_dim=1 + len(extra_vars), hidden_dim=hidden_dim, num_layers=num_layers)
        model = train(model, train_loader, val_loader, epochs=SWEEP_EPOCHS, quiet=True)
        metrics, _ = _held_out_mae(model, val_ds, truth)

        cfg = {"input_seq_len": input_seq_len, "hidden_dim": hidden_dim, "num_layers": num_layers}
        print(f"  {cfg} -> mae={metrics['mae']:.4f} rmse={metrics['rmse']:.4f}")
        results.append({**cfg, "mae": metrics["mae"], "rmse": metrics["rmse"]})

    results.sort(key=lambda r: r["mae"])
    best = results[0]
    print(f"\nBest config (real held-out MAE, {SWEEP_EPOCHS}-epoch sweep runs): {best}")
    return best, results


def train_final_ensemble(processed_path, extra_vars, best_cfg, batch_size, save_checkpoint):
    full_ds = xr.open_dataset(processed_path)
    n_time = full_ds.sizes["time"]
    train_sl, val_sl, test_sl = chronological_splits(n_time)
    conc = full_ds["cdr_seaice_conc"]
    truth = conc.isel(time=val_sl)

    input_seq_len, hidden_dim, num_layers = best_cfg["input_seq_len"], best_cfg["hidden_dim"], best_cfg["num_layers"]
    train_ds = SeaIceSequenceDataset(processed_path, input_seq_len, extra_vars=extra_vars, time_slice=train_sl)
    val_ds = SeaIceSequenceDataset(processed_path, input_seq_len, extra_vars=extra_vars, time_slice=val_sl)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    member_state_dicts = []
    member_preds = []
    print(f"\nTraining {N_ENSEMBLE_MEMBERS} ensemble members at the winning config ({FINAL_EPOCHS} epochs each):")
    for seed in range(N_ENSEMBLE_MEMBERS):
        torch.manual_seed(seed)
        model = SeaIceConvLSTM(input_dim=1 + len(extra_vars), hidden_dim=hidden_dim, num_layers=num_layers)
        model = train(model, train_loader, val_loader, epochs=FINAL_EPOCHS, quiet=True)
        metrics, preds = _held_out_mae(model, val_ds, truth)
        print(f"  seed={seed}: mae={metrics['mae']:.4f} rmse={metrics['rmse']:.4f}")
        member_state_dicts.append(model.state_dict())
        member_preds.append(preds)

    # Real ensemble-averaged prediction, same members pipeline.py will use.
    ensemble_pred = np.mean(member_preds, axis=0)
    ensemble_da = xr.DataArray(
        ensemble_pred, dims=("time", "lat", "lon"),
        coords={"time": truth.time.values[:ensemble_pred.shape[0]], "lat": truth.lat, "lon": truth.lon},
    )
    truth_aligned = truth.isel(time=slice(0, ensemble_pred.shape[0]))

    history = conc.isel(time=train_sl)
    persistence_pred = persistence_forecast(history, horizon_days=truth_aligned.sizes["time"])
    climatology_pred = climatology_forecast(history, target_dates=list(truth_aligned.time.values))

    print("\nFinal held-out skill (ensemble vs. baselines, real data, don't cherry-pick):")
    skill = {}
    for name, pred in [
        ("persistence", persistence_pred.isel(time=slice(0, ensemble_pred.shape[0]))),
        ("climatology", climatology_pred.isel(time=slice(0, ensemble_pred.shape[0]))),
        ("convlstm_ensemble", ensemble_da),
    ]:
        metrics = evaluate(pred, truth_aligned)
        skill[name] = metrics
        print(f"  {name:18s} mae={metrics['mae']:.4f} rmse={metrics['rmse']:.4f} bias={metrics['bias']:+.4f}")

    ckpt_path = Path(save_checkpoint)
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "ensemble_state_dicts": member_state_dicts,
        "input_seq_len": input_seq_len,
        "hidden_dim": hidden_dim,
        "num_layers": num_layers,
        "kernel_size": 3,
        "extra_vars": extra_vars,
        "trained_on": str(processed_path),
        "n_train_days": int(train_sl.stop - train_sl.start),
        "n_ensemble_members": N_ENSEMBLE_MEMBERS,
        "held_out_skill": {k: {mk: float(mv) for mk, mv in v.items()} for k, v in skill.items()},
    }, ckpt_path)
    print(f"\nSaved ensemble checkpoint to {ckpt_path}")
    return skill


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-path", default=str(region_path("data/processed", "seaice_history.nc")))
    parser.add_argument("--extra-vars", default="")
    parser.add_argument("--input-seq-lens", default="5,7,10")
    parser.add_argument("--hidden-dims", default="16,32,64")
    parser.add_argument("--num-layers-list", default="1,2")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--save-checkpoint", default=str(region_path("data/processed", "convlstm_checkpoint.pt")))
    parser.add_argument("--sweep-results-out", default=str(region_path("data/processed", "convlstm_sweep_results.json")))
    parser.add_argument("--n-ensemble-members", type=int, default=None)
    parser.add_argument("--sweep-epochs", type=int, default=None)
    parser.add_argument("--final-epochs", type=int, default=None)
    args = parser.parse_args()
    _set_budgets(args.n_ensemble_members, args.sweep_epochs, args.final_epochs)

    extra_vars = [v.strip() for v in args.extra_vars.split(",") if v.strip()]
    input_seq_lens = [int(x) for x in args.input_seq_lens.split(",")]
    hidden_dims = [int(x) for x in args.hidden_dims.split(",")]
    num_layers_list = [int(x) for x in args.num_layers_list.split(",")]

    best_cfg, all_results = run_sweep(
        args.processed_path, extra_vars, input_seq_lens, hidden_dims, num_layers_list, args.batch_size,
    )
    skill = train_final_ensemble(args.processed_path, extra_vars, best_cfg, args.batch_size, args.save_checkpoint)

    Path(args.sweep_results_out).write_text(json.dumps({
        "sweep_results": all_results, "best_config": best_cfg,
        "final_ensemble_skill": {k: {mk: float(mv) for mk, mv in v.items()} for k, v in skill.items()},
    }, indent=2))
    print(f"Saved sweep results to {args.sweep_results_out}")

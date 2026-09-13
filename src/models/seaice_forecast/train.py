"""
Module 1, step 3 — training loop for SeaIceConvLSTM.

Fill in once preprocess.py is producing clean, gridded, gap-free training
data (Phase 1 must be solid before this can start — a training loop
running on shaky preprocessing just produces confidently wrong models).
"""

import numpy as np
import torch
import xarray as xr
from torch.utils.data import Dataset, DataLoader

from .convlstm import SeaIceConvLSTM
from .baseline import evaluate


class SeaIceSequenceDataset(Dataset):
    """
    Wraps the processed NetCDF history (data/processed/, already regridded
    onto the shared lat/lon grid by preprocess.py) into (input_sequence,
    target) pairs — a sliding window of `input_seq_len` days predicting
    the next day's concentration.

    Optionally concatenates extra forcing channels (e.g. regridded ERA5
    u/v wind) alongside concentration, since the ConvLSTM's input_dim can
    be >1 (see convlstm.py's TODO).

    Chronological split only (no shuffling across the time axis) — sea-ice
    concentration is highly autocorrelated day-to-day, so a random split
    leaks future information into training and produces misleadingly good
    validation numbers. Slice by index range (e.g. dataset[:n_train]'s
    underlying time range) rather than torch's random_split.
    """

    def __init__(self, processed_path, input_seq_len: int = 7,
                 conc_var: str = "cdr_seaice_conc", extra_vars: list = None,
                 time_slice: slice = None):
        self.input_seq_len = input_seq_len
        ds = xr.open_dataset(processed_path)
        if time_slice is not None:
            ds = ds.isel(time=time_slice)

        conc = ds[conc_var].values.astype(np.float32)  # (time, lat, lon)
        if np.isnan(conc).any():
            raise ValueError(
                f"{processed_path}'s '{conc_var}' has NaNs — preprocess.py's "
                "regridding should produce gap-free data over the domain; "
                "fill gaps (e.g. temporal interpolation) before training, "
                "don't silently zero-fill sea-ice concentration."
            )

        channels = [conc]
        for var in (extra_vars or []):
            channels.append(ds[var].values.astype(np.float32))
        # (time, channel, lat, lon)
        self.data = np.stack(channels, axis=1)

        n_time = self.data.shape[0]
        if n_time <= input_seq_len:
            raise ValueError(
                f"Only {n_time} timesteps available, need > input_seq_len "
                f"({input_seq_len}) to form even one training example."
            )
        self.n_samples = n_time - input_seq_len

    def __len__(self):
        return self.n_samples

    def __getitem__(self, idx):
        x_seq = self.data[idx: idx + self.input_seq_len]           # (seq_len, channel, lat, lon)
        target = self.data[idx + self.input_seq_len, 0:1]          # (1, lat, lon) -- concentration only
        return torch.from_numpy(x_seq), torch.from_numpy(target)


def train(model, train_loader, val_loader, epochs: int = 20, lr: float = 1e-3, device: str = "cpu"):
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = torch.nn.MSELoss()

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        for x_seq, target in train_loader:
            x_seq, target = x_seq.to(device), target.to(device)
            optimizer.zero_grad()
            pred = model(x_seq)
            loss = loss_fn(pred, target)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for x_seq, target in val_loader:
                x_seq, target = x_seq.to(device), target.to(device)
                pred = model(x_seq)
                val_loss += loss_fn(pred, target).item()

        print(f"Epoch {epoch+1}/{epochs} — train_loss={train_loss/len(train_loader):.4f} "
              f"val_loss={val_loss/len(val_loader):.4f}")

    return model


def chronological_splits(n_time: int, train_frac=0.7, val_frac=0.15):
    """Index ranges for a strict time-ordered train/val/test split — no
    shuffling across the boundary, per this module's own warning above."""
    n_train = int(n_time * train_frac)
    n_val = int(n_time * val_frac)
    return (
        slice(0, n_train),
        slice(n_train, n_train + n_val),
        slice(n_train + n_val, n_time),
    )


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-path", default="data/processed/seaice_history.nc")
    parser.add_argument("--input-seq-len", type=int, default=7)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--save-checkpoint", default="data/processed/convlstm_checkpoint.pt",
                         help="Where to save the trained model — src/integration/pipeline.py's "
                              "get_seaice_concentration() looks for a checkpoint at exactly this "
                              "default path and switches from persistence to real inference "
                              "the moment one exists.")
    args = parser.parse_args()

    if not Path(args.processed_path).exists():
        print(
            f"{args.processed_path} not found — run src/data/download_seaice_bremen.py "
            "--start ... --end ... then src/data/build_seaice_history.py first to produce "
            "real processed history before training on it (or src/data/download_seaice.py + "
            "preprocess.py, once NSIDC credentials exist)."
        )
        raise SystemExit(1)

    full_ds = xr.open_dataset(args.processed_path)
    n_time = full_ds.sizes["time"]
    train_sl, val_sl, test_sl = chronological_splits(n_time)
    print(f"{n_time} total days -> train={train_sl}, val={val_sl}, test={test_sl}")

    train_ds = SeaIceSequenceDataset(args.processed_path, args.input_seq_len, time_slice=train_sl)
    val_ds = SeaIceSequenceDataset(args.processed_path, args.input_seq_len, time_slice=val_sl)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=False)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    model = SeaIceConvLSTM(input_dim=1)
    model = train(model, train_loader, val_loader, epochs=args.epochs)

    # Compare against baselines on the same held-out (val) window — the
    # comparison table is the deliverable, not just the trained model.
    conc = full_ds["cdr_seaice_conc"]
    history = conc.isel(time=train_sl)
    truth = conc.isel(time=val_sl)

    persistence_pred = baseline_persistence = None
    from .baseline import persistence_forecast, climatology_forecast
    persistence_pred = persistence_forecast(history, horizon_days=truth.sizes["time"])
    climatology_pred = climatology_forecast(history, target_dates=list(truth.time.values))

    model.eval()
    convlstm_preds = []
    with torch.no_grad():
        for i in range(len(val_ds)):
            x_seq, _ = val_ds[i]
            pred = model(x_seq.unsqueeze(0)).squeeze(0).squeeze(0).numpy()
            convlstm_preds.append(pred)
    convlstm_pred = xr.DataArray(
        np.stack(convlstm_preds), dims=("time", "lat", "lon"),
        coords={"time": truth.time.values[: len(convlstm_preds)], "lat": truth.lat, "lon": truth.lon},
    )
    truth_aligned = truth.isel(time=slice(0, len(convlstm_preds)))

    print("\nHeld-out skill (lower is better; report honestly, don't cherry-pick):")
    skill = {}
    for name, pred in [
        ("persistence", persistence_pred.isel(time=slice(0, len(convlstm_preds)))),
        ("climatology", climatology_pred.isel(time=slice(0, len(convlstm_preds)))),
        ("convlstm", convlstm_pred),
    ]:
        metrics = evaluate(pred, truth_aligned)
        skill[name] = metrics
        print(f"  {name:12s} mae={metrics['mae']:.4f} rmse={metrics['rmse']:.4f} bias={metrics['bias']:+.4f}")

    if skill["convlstm"]["mae"] >= skill["persistence"]["mae"]:
        print(
            "\nNOTE: the trained model did not beat persistence on held-out MAE. Per this "
            "module's own docstring (and the 'Should Sea-Ice Modeling Tools...' paper cited in "
            "the README), that's not unheard-of at short lead times -- saving the checkpoint "
            "anyway since pipeline.py's get_seaice_concentration() should still report this "
            "honestly rather than silently keep using persistence, but flag it in the app's "
            "disclosure rather than presenting it as a clear win."
        )

    ckpt_path = Path(args.save_checkpoint)
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_state_dict": model.state_dict(),
        "input_seq_len": args.input_seq_len,
        "trained_on": args.processed_path,
        "n_train_days": int(train_sl.stop - train_sl.start),
        "held_out_skill": {k: {mk: float(mv) for mk, mv in v.items()} for k, v in skill.items()},
    }, ckpt_path)
    print(f"Saved checkpoint to {ckpt_path}")

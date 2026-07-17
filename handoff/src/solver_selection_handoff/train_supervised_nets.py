"""
Train supervised networks (CPU + error) from solver_dataset.npy.

Dataset layout (per row):
  [T, P, Y_0..Y_{n-1}, cvode_cpu, cvode_temp_err, cvode_species_err, qss_cpu, qss_temp_err, qss_species_err]

Paper-style inputs:
  [log(Y_1)..log(Y_k), T, p, log(dt)]
    - Y clipped to 1e-20 before log
    - log(dt) used since dt spans scales (here may be constant unless you regenerate varying dt)
    - inputs normalized to mean 0, std 1 using train split stats

Targets:
  - CPU net: [cvode_cpu, qss_cpu]  (no transform)
  - Error net: [log(err_cvode), log(err_qss)]
      where err_* defaults to composite error = alpha_T*temp_err + alpha_Y*species_err

Architectures (as in the paper excerpt):
  - error net: 3 hidden layers: 1024, 512, 256 (ReLU)
  - cpu  net: 5 hidden layers: 256, 256, 256, 256, 128 (ReLU)

Training:
  - Adam, lr=1e-3
  - up to 200 epochs, batch size 512
  - ReduceLROnPlateau factor 5 when val loss plateaus

Outputs:
  - saves checkpoints + normalizer + metadata into an output directory.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Literal, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset


EPS_Y = 1e-20
EPS_ERR = 1e-30


class NpyMemmapDataset(Dataset):
    def __init__(self, data: np.ndarray, idx: np.ndarray):
        self.data = data
        self.idx = idx

    def __len__(self) -> int:
        return int(self.idx.shape[0])

    def __getitem__(self, i: int):
        row = self.data[self.idx[i]]
        return row


class MLP(nn.Module):
    def __init__(self, in_dim: int, hidden: List[int], out_dim: int):
        super().__init__()
        layers: List[nn.Module] = []
        prev = in_dim
        for h in hidden:
            layers.append(nn.Linear(prev, h))
            layers.append(nn.ReLU())
            prev = h
        layers.append(nn.Linear(prev, out_dim))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


@dataclass
class TrainConfig:
    batch_size: int = 512
    epochs: int = 200
    lr: float = 1e-3
    weight_decay: float = 0.0
    patience: int = 10
    lr_factor: float = 0.2  # /5
    min_lr: float = 1e-6


def parse_args():
    p = argparse.ArgumentParser(description="Train supervised CPU + error nets from solver_dataset.npy")
    p.add_argument("--data", type=str, default="solver_dataset.npy", help="Path to .npy dataset")
    p.add_argument("--outdir", type=str, default="supervised_models", help="Output directory for models")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--device", type=str, default="cpu", choices=["cpu", "cuda"])

    p.add_argument("--dt", type=float, default=1e-6, help="CFD timestep to include (used if dataset doesn't include dt)")
    p.add_argument("--pressure-unit", type=str, default="bar", choices=["pa", "bar"])

    p.add_argument("--input-mode", type=str, default="full",
                   choices=["full", "h2o2_12"],
                   help="Feature set: full species or 12-input case (9 H2/O2 submech species + T,p,dt).")
    p.add_argument("--mechanism-file", type=str, default=None,
                   help="Cantera mechanism file used to map species for h2o2_12 (e.g. 'h2o2.yaml').")

    p.add_argument("--alpha-T", type=float, default=0.7)
    p.add_argument("--alpha-Y", type=float, default=0.3)

    p.add_argument("--train-frac", type=float, default=0.8)
    p.add_argument("--val-frac", type=float, default=0.1)
    p.add_argument("--max-samples", type=int, default=0, help="If >0, subsample this many rows (debug).")
    return p.parse_args()


def get_h2o2_9_species_indices(mech_file: str) -> Tuple[List[int], List[str]]:
    import cantera as ct

    gas = ct.Solution(mech_file)
    # Common 9-species H2/O2 submechanism (+ N2)
    names = ["H2", "O2", "H", "O", "OH", "HO2", "H2O", "H2O2", "N2"]
    idxs: List[int] = []
    missing: List[str] = []
    for sp in names:
        try:
            idxs.append(gas.species_index(sp))
        except Exception:
            missing.append(sp)
    if missing:
        raise ValueError(f"Missing required species in mechanism {mech_file}: {missing}")
    return idxs, names


def build_features_and_targets(
    batch_rows: np.ndarray,
    n_species: int,
    dt_value: float,
    pressure_unit: Literal["pa", "bar"],
    alpha_T: float,
    alpha_Y: float,
    input_mode: Literal["full", "h2o2_12"],
    h2o2_species_indices: List[int] | None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns:
      X: [B, d_in]
      y_cpu: [B, 2]  (cvode_cpu, qss_cpu)
      y_logerr: [B, 2] (log(err_cvode), log(err_qss))
    """
    # Layout
    # state = [T, P, Y...]
    T = batch_rows[:, 0:1].astype(np.float32)
    P = batch_rows[:, 1:2].astype(np.float32)
    Y = batch_rows[:, 2:2 + n_species].astype(np.float32)

    if pressure_unit == "bar":
        P = P / 101325.0

    Y_clip = np.clip(Y, EPS_Y, 1.0)
    logY = np.log10(Y_clip).astype(np.float32)

    logdt = np.log10(np.array([[dt_value]], dtype=np.float32))
    logdt = np.repeat(logdt, repeats=batch_rows.shape[0], axis=0)

    if input_mode == "full":
        X = np.concatenate([logY, T, P, logdt], axis=1)
    else:
        assert h2o2_species_indices is not None
        X = np.concatenate([logY[:, h2o2_species_indices], T, P, logdt], axis=1)

    # Targets
    # [cvode_cpu, cvode_temp_err, cvode_species_err, qss_cpu, qss_temp_err, qss_species_err]
    tail = batch_rows[:, 2 + n_species:]
    cv_cpu = tail[:, 0:1].astype(np.float32)
    cv_te = tail[:, 1:2].astype(np.float32)
    cv_ye = tail[:, 2:3].astype(np.float32)
    qs_cpu = tail[:, 3:4].astype(np.float32)
    qs_te = tail[:, 4:5].astype(np.float32)
    qs_ye = tail[:, 5:6].astype(np.float32)

    y_cpu = np.concatenate([cv_cpu, qs_cpu], axis=1)

    err_cv = alpha_T * cv_te + alpha_Y * cv_ye
    err_qs = alpha_T * qs_te + alpha_Y * qs_ye
    y_logerr = np.concatenate(
        [
            np.log10(np.clip(err_cv, EPS_ERR, None)),
            np.log10(np.clip(err_qs, EPS_ERR, None)),
        ],
        axis=1,
    ).astype(np.float32)

    return X, y_cpu, y_logerr


def compute_normalizer(
    data: np.ndarray,
    idx_train: np.ndarray,
    n_species: int,
    args,
    h2o2_species_indices: List[int] | None,
) -> Tuple[np.ndarray, np.ndarray]:
    X_train, _, _ = build_features_and_targets(
        data[idx_train],
        n_species=n_species,
        dt_value=args.dt,
        pressure_unit=args.pressure_unit,
        alpha_T=args.alpha_T,
        alpha_Y=args.alpha_Y,
        input_mode=args.input_mode,
        h2o2_species_indices=h2o2_species_indices,
    )
    mean = X_train.mean(axis=0)
    std = X_train.std(axis=0)
    std = np.where(std < 1e-12, 1.0, std)
    return mean.astype(np.float32), std.astype(np.float32)


@torch.no_grad()
def evaluate(model: nn.Module, loader: DataLoader, device: torch.device, loss_fn):
    model.eval()
    losses = []
    for rows in loader:
        rows = rows.numpy()
        yield rows


def train_one(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    device: torch.device,
    optimizer: torch.optim.Optimizer,
    scheduler,
    loss_fn,
    make_batch,
    out_path: Path,
    epochs: int,
):
    best_val = float("inf")
    best_state = None
    plateau_count = 0

    for epoch in range(1, epochs + 1):
        model.train()
        train_losses = []
        for rows in train_loader:
            rows = rows.numpy()
            x, y = make_batch(rows)
            x_t = torch.from_numpy(x).to(device)
            y_t = torch.from_numpy(y).to(device)

            pred = model(x_t)
            loss = loss_fn(pred, y_t)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_losses.append(loss.item())

        # Validation
        model.eval()
        val_losses = []
        with torch.no_grad():
            for rows in val_loader:
                rows = rows.numpy()
                x, y = make_batch(rows)
                x_t = torch.from_numpy(x).to(device)
                y_t = torch.from_numpy(y).to(device)
                pred = model(x_t)
                val_losses.append(loss_fn(pred, y_t).item())

        train_loss = float(np.mean(train_losses)) if train_losses else float("nan")
        val_loss = float(np.mean(val_losses)) if val_losses else float("nan")
        scheduler.step(val_loss)

        lr = optimizer.param_groups[0]["lr"]
        print(f"epoch {epoch:3d} | train={train_loss:.6e} | val={val_loss:.6e} | lr={lr:.2e}")

        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            plateau_count = 0
        else:
            plateau_count += 1

        if lr <= scheduler.min_lrs[0] + 1e-12 and plateau_count >= 10:
            break

    if best_state is not None:
        model.load_state_dict(best_state)
        torch.save({"state_dict": model.state_dict()}, out_path)
        print(f"saved best model -> {out_path} (best val={best_val:.6e})")


def main():
    args = parse_args()
    rng = np.random.default_rng(args.seed)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    data_path = Path(args.data)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    data = np.load(data_path, mmap_mode="r")
    n_cols = data.shape[1]

    # Infer n_species from last 6 metrics columns and leading [T, P, Y...]
    # n_cols = 2 + n_species + 6
    if n_cols < 2 + 6 + 1:
        raise ValueError(f"Unexpected dataset shape: {data.shape}")
    n_species = n_cols - 8

    h2o2_species_indices = None
    input_dim = None
    if args.input_mode == "h2o2_12":
        if not args.mechanism_file:
            raise ValueError("--mechanism-file is required for --input-mode h2o2_12")
        h2o2_species_indices, h2o2_names = get_h2o2_9_species_indices(args.mechanism_file)
        input_dim = 9 + 3  # 9 species + T + p + dt
    else:
        input_dim = n_species + 3  # all species + T + p + dt

    # Indices / split
    N = data.shape[0]
    idx = np.arange(N)
    rng.shuffle(idx)
    if args.max_samples and args.max_samples > 0:
        idx = idx[: args.max_samples]
        N = idx.shape[0]

    n_train = int(N * args.train_frac)
    n_val = int(N * args.val_frac)
    idx_train = idx[:n_train]
    idx_val = idx[n_train:n_train + n_val]
    idx_test = idx[n_train + n_val:]

    # Normalizer from train split
    x_mean, x_std = compute_normalizer(
        data, idx_train, n_species=n_species, args=args, h2o2_species_indices=h2o2_species_indices
    )

    def make_batch_cpu(rows: np.ndarray):
        X, y_cpu, _ = build_features_and_targets(
            rows, n_species=n_species, dt_value=args.dt, pressure_unit=args.pressure_unit,
            alpha_T=args.alpha_T, alpha_Y=args.alpha_Y, input_mode=args.input_mode,
            h2o2_species_indices=h2o2_species_indices,
        )
        X = (X - x_mean) / x_std
        return X, y_cpu

    def make_batch_err(rows: np.ndarray):
        X, _, y_logerr = build_features_and_targets(
            rows, n_species=n_species, dt_value=args.dt, pressure_unit=args.pressure_unit,
            alpha_T=args.alpha_T, alpha_Y=args.alpha_Y, input_mode=args.input_mode,
            h2o2_species_indices=h2o2_species_indices,
        )
        X = (X - x_mean) / x_std
        return X, y_logerr

    # Dataloaders (store only indices; rows are fetched via memmap)
    train_ds = NpyMemmapDataset(data, idx_train)
    val_ds = NpyMemmapDataset(data, idx_val)
    test_ds = NpyMemmapDataset(data, idx_test)

    cfg = TrainConfig()
    device = torch.device(args.device)

    train_loader = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=0)

    # Models
    cpu_net = MLP(input_dim, hidden=[256, 256, 256, 256, 128], out_dim=2).to(device)
    err_net = MLP(input_dim, hidden=[1024, 512, 256], out_dim=2).to(device)

    # Optimizers + schedulers
    cpu_opt = torch.optim.Adam(cpu_net.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    err_opt = torch.optim.Adam(err_net.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)

    cpu_sched = torch.optim.lr_scheduler.ReduceLROnPlateau(
        cpu_opt, mode="min", factor=cfg.lr_factor, patience=cfg.patience, min_lr=cfg.min_lr
    )
    err_sched = torch.optim.lr_scheduler.ReduceLROnPlateau(
        err_opt, mode="min", factor=cfg.lr_factor, patience=cfg.patience, min_lr=cfg.min_lr
    )

    mse = nn.MSELoss()

    # Save metadata/normalizer
    meta = {
        "data": str(data_path),
        "n_rows": int(N),
        "n_species": int(n_species),
        "input_mode": args.input_mode,
        "pressure_unit": args.pressure_unit,
        "dt": float(args.dt),
        "alpha_T": float(args.alpha_T),
        "alpha_Y": float(args.alpha_Y),
        "input_dim": int(input_dim),
        "h2o2_species_indices": h2o2_species_indices,
        "splits": {
            "train": int(idx_train.shape[0]),
            "val": int(idx_val.shape[0]),
            "test": int(idx_test.shape[0]),
        },
    }
    (outdir / "meta.json").write_text(json.dumps(meta, indent=2))
    np.savez(outdir / "normalizer.npz", mean=x_mean, std=x_std)

    print(f"Dataset: {data_path} | rows={N:,} | n_species={n_species} | input_dim={input_dim}")
    print(f"Saving to: {outdir}")

    print("\n=== Train CPU net ===")
    train_one(
        cpu_net, train_loader, val_loader, device,
        cpu_opt, cpu_sched, mse, make_batch_cpu,
        out_path=outdir / "cpu_net.pt",
        epochs=cfg.epochs,
    )

    print("\n=== Train Error net (log10) ===")
    train_one(
        err_net, train_loader, val_loader, device,
        err_opt, err_sched, mse, make_batch_err,
        out_path=outdir / "err_net.pt",
        epochs=cfg.epochs,
    )

    print("\nDone.")


if __name__ == "__main__":
    main()


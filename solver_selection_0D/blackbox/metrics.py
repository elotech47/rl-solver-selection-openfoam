"""Ignition delay and range-normalized temperature error metrics."""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


def ignition_delay_s(
    trajectory: Optional[np.ndarray],
    dt: float,
) -> Optional[float]:
    """Ignition delay = time of maximum dT/dt (seconds)."""
    if trajectory is None or len(trajectory) < 2:
        return None
    temps = np.asarray(trajectory[:, 0], dtype=float)
    dT = np.diff(temps) / float(dt)
    idx = int(np.argmax(dT))
    return float(idx * dt)


def range_normalized_temp_mse(
    method_traj: np.ndarray,
    ref_traj: np.ndarray,
    *,
    eps: float = 1e-10,
) -> Tuple[float, float]:
    """
    Min–max normalize temperature using the *reference* range, then MSE / RMSE.

        T_hat = (T - T_ref_min) / (T_ref_max - T_ref_min + eps)
        MSE   = mean( (T_hat_method - T_hat_ref)^2 )

    Returns
    -------
    (mse, rmse)
    """
    m = min(len(method_traj), len(ref_traj))
    if m < 1:
        return float("nan"), float("nan")

    t_m = np.asarray(method_traj[:m, 0], dtype=float)
    t_r = np.asarray(ref_traj[:m, 0], dtype=float)
    t_min = float(np.min(ref_traj[:, 0]))
    t_max = float(np.max(ref_traj[:, 0]))
    denom = max(t_max - t_min, eps)

    err = (t_m - t_r) / denom
    mse = float(np.mean(err ** 2))
    return mse, float(np.sqrt(mse))


def primary_solver(label: str) -> str:
    """Map ``'CVODE->QSS'`` style fallback labels to the primary solver."""
    return str(label).split("->")[0].strip().upper()

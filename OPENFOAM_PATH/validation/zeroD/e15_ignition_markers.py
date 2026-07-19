#!/usr/bin/env python3
"""T0-robust ignition markers shared by OF and Python E15 maps.

main  = time of global max dT/dt
first = first local dT/dt peak that is clearly separated from main
        (cool-flame / first-stage). Requires a valley between first and main.
"""
from __future__ import annotations

import numpy as np


def dTdt(t: np.ndarray, T: np.ndarray) -> np.ndarray:
    t = np.asarray(t, dtype=float)
    T = np.asarray(T, dtype=float)
    if len(t) < 3:
        return np.zeros_like(t)
    # Guard duplicate times (timeout stall / collapsed Δt)
    t_work = t.copy()
    for i in range(1, len(t_work)):
        if t_work[i] <= t_work[i - 1]:
            t_work[i] = t_work[i - 1] + 1e-18
    return np.gradient(T, t_work)


def tau_main(t: np.ndarray, T: np.ndarray) -> float:
    t = np.asarray(t, dtype=float)
    T = np.asarray(T, dtype=float)
    if len(t) < 3:
        return float("nan")
    g = dTdt(t, T)
    mask = t > max(1e-7, 0.001 * (t[-1] - t[0] + 1e-30))
    if not np.any(mask):
        mask = np.ones_like(t, dtype=bool)
    i = int(np.argmax(np.where(mask, g, -np.inf)))
    if not np.isfinite(g[i]) or g[i] <= 0:
        return float("nan")
    return float(t[i])


def _local_peaks(g: np.ndarray, t: np.ndarray, thr: float, t_hi: float):
    out = []
    for i in range(1, len(t) - 1):
        if t[i] > t_hi or t[i] < 1e-7:
            continue
        if g[i] >= thr and g[i] > g[i - 1] and g[i] >= g[i + 1]:
            out.append(i)
    return out


def tau_first(
    t: np.ndarray,
    T: np.ndarray,
    *,
    min_frac_of_main_peak: float = 0.06,
    max_frac_of_main_time: float = 0.80,
    valley_frac: float = 0.45,
) -> float:
    """First-stage peak: early local max of dT/dt with a valley before main.

    Thresholds tuned so OF (first-stage ~7–9% of main peak) and Python agree
    on NTC lean cases; high-T near-main shoulders are rejected via valley test
    + max_frac_of_main_time.
    """
    t = np.asarray(t, dtype=float)
    T = np.asarray(T, dtype=float)
    if len(t) < 5:
        return float("nan")
    g = dTdt(t, T)
    gmax = float(np.nanmax(g))
    if not np.isfinite(gmax) or gmax <= 0:
        return float("nan")
    t_m = tau_main(t, T)
    if not np.isfinite(t_m):
        return float("nan")
    i_m = int(np.argmin(np.abs(t - t_m)))
    thr = min_frac_of_main_peak * gmax
    t_cut = max_frac_of_main_time * t_m
    for i in _local_peaks(g, t, thr, t_cut):
        if i >= i_m:
            continue
        # Valley between candidate and main must dip below valley_frac * min(peaks)
        g_lo = float(np.min(g[i : i_m + 1]))
        peak_ref = min(float(g[i]), float(g[i_m]))
        if g_lo <= valley_frac * peak_ref:
            return float(t[i])
    return float("nan")


def ignition_metrics(t, T) -> dict:
    t = np.asarray(t, dtype=float)
    T = np.asarray(T, dtype=float)
    return dict(
        tau_main_s=tau_main(t, T),
        tau_first_s=tau_first(t, T),
        Teq=float(T[-1]) if len(T) else float("nan"),
        T0=float(T[0]) if len(T) else float("nan"),
        T_max=float(np.nanmax(T)) if len(T) else float("nan"),
    )

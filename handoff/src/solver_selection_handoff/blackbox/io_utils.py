"""Pickle / CSV / JSON persistence for black-box evaluation results."""

from __future__ import annotations

import csv
import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional


TIMING_STATS_KEY = "__cpu_timing__"


def save_results_pkl(results: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(results, f, protocol=pickle.HIGHEST_PROTOCOL)


def load_results_pkl(path: Path) -> dict:
    with open(path, "rb") as f:
        return pickle.load(f)


def save_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def _default(o: Any) -> Any:
        if isinstance(o, Path):
            return str(o)
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=_default)


def write_summary_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # Stable column order: union of keys, condition first.
    keys: List[str] = []
    for row in rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    if "condition" in keys:
        keys = ["condition"] + [k for k in keys if k != "condition"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def get_cpu_mean_std(results: dict, method: str) -> tuple[float, float]:
    timing = results.get(TIMING_STATS_KEY, {})
    if method in timing:
        return float(timing[method]["mean"]), float(timing[method]["std"])
    r = results.get(method)
    if r is None:
        return float("nan"), float("nan")
    return float(r.cpu_time), 0.0


def condition_pkl_name(temp: float, pressure_atm: float, Z: float) -> str:
    return f"condition_{temp:.0f}K_{pressure_atm:.1f}atm_{Z}.pkl"

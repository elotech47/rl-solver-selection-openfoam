#!/usr/bin/env python3
"""E16.4 Python pipeline counterparts: CVODE, QSS, AdaptiveRL for paper conditions."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CONDS = ROOT / "validation/e16_parity/E16_4_CONDITIONS.json"
OUT = ROOT / "validation/e16_parity/e16_4_runs"
CKPT = ROOT / "policy/best_offline_eval2.pt"
MECH = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
HANDOFF = Path("/Users/el0tech/Documents/research_code/solver_selection/handoff/src")
KEY = ["oh", "h2o", "o2", "h2", "h2o2", "o", "h", "n2"]
FUEL = "nc12h26:1.0"
OX = "o2:1.0, n2:3.76"


def ignition_delay(temps: np.ndarray, times: np.ndarray) -> float | None:
    if temps is None or len(temps) < 2:
        return None
    if (temps[-1] - temps[0]) <= 10 and temps[0] <= 1000:
        return 0.0
    dT = np.diff(temps) / np.diff(times)
    return float(times[int(np.argmax(dT))])


def ood_fraction(ps: np.ndarray) -> float:
    if len(ps) == 0:
        return float("nan")
    return float(np.mean(np.abs(ps - 0.5) < 0.1))


def run_condition(c: dict) -> dict:
    sys.path.insert(0, str(HANDOFF))
    import cantera as ct
    from solver_selection_handoff.inference import RLSolverSelector
    from solver_selection_handoff.evaluation_pipeline import CompletePipeline

    if not CKPT.is_file():
        raise FileNotFoundError(CKPT)

    selector = RLSolverSelector(
        model_path=str(CKPT),
        mechanism_file=str(MECH),
        device="cpu",
        network_config={"hidden_dims": [256, 128, 64], "activation": "relu"},
        key_species=KEY,
        use_prev_state=True,
        use_gradient_only=False,
        confidence_threshold=0.6,
    )
    selector.reset()

    condition = {
        "temp": c["T0"],
        "pressure": c["p_atm"] * ct.one_atm,
        "Z": c["Z"],
        "fuel": FUEL,
        "oxidizer": OX,
        "dt": c["dt"],
        "t_end": c["t_end"],
        "key_species": KEY,
    }
    config = {
        "num_steps": c["num_steps"],
        "use_prev_state": True,
        "use_gradient_only": False,
        "epsmin": 0.02,
        "epsmax": 100.0,
        "dtmin": 1e-12,
        "dtmax": 1e-6,
        "abstol": 1e-11,
        "itermax": 2,
        "rtol": 1e-8,
        "atol": 1e-12,
    }

    pipeline = CompletePipeline(
        mechanism=str(MECH),
        condition=condition,
        config=config,
        rl_selector=selector,
        confidence_threshold=0.6,
        record_rl_decisions=True,
    )

    strategies = pipeline._initialize_strategies()
    names = ("CVODE", "QSS", "RL-Adaptive")
    results = {}
    summary = {
        "id": c["id"],
        "label": c["label"],
        "T0": c["T0"],
        "p_atm": c["p_atm"],
        "Z": c["Z"],
        "dt": c["dt"],
        "t_end": c["t_end"],
        "maxChemDeltaT": c["dt"],
        "num_steps": c["num_steps"],
        "decision_interval_s": c["dt"] * c["num_steps"],
        "source": "handoff/configs/example_ndodecane.yaml",
        "modes": {},
    }

    out_dir = OUT / f"{c['id']}_python"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in names:
        print(f"[e16.4 py] {c['id']} {name} ...", flush=True)
        t0 = time.perf_counter()
        res = pipeline.evaluator.evaluate(
            strategies[name],
            pipeline.initial_state.copy(),
            None,
        )
        wall = time.perf_counter() - t0
        traj = np.asarray(getattr(res, "trajectory", None))
        times = np.asarray(getattr(res, "times", None))
        temps = traj[:, 0] if traj is not None and len(traj) else np.array([])
        tau = ignition_delay(temps, times) if len(temps) else None
        mode_key = {"CVODE": "CVODE", "QSS": "QSS", "RL-Adaptive": "AdaptiveRL"}[name]
        np.savez_compressed(
            out_dir / f"{mode_key}_traj.npz",
            times=times,
            T=temps,
            cpu_time=float(getattr(res, "cpu_time", 0.0)),
            wall_time=float(getattr(res, "wall_time", wall) or wall),
        )
        entry = {
            "T_final": float(temps[-1]) if len(temps) else None,
            "tau_ign": tau,
            "cpu_time": float(getattr(res, "cpu_time", 0.0)),
            "wall_time": float(getattr(res, "wall_time", wall) or wall),
            "n_steps": int(len(temps)),
        }
        results[name] = res
        summary["modes"][mode_key] = entry

    # RL decisions + OOD (p = P(QSS) = probs[1])
    rl = strategies["RL-Adaptive"]
    log = list(getattr(rl, "rl_decision_log", []) or [])
    rl_res = results["RL-Adaptive"]
    traj = np.asarray(getattr(rl_res, "trajectory", None))
    times = np.asarray(getattr(rl_res, "times", None))
    with (out_dir / "decisions.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            ["step_index", "time", "T", "executed_action", "policy_action", "conf", "p"]
        )
        ps = []
        flags = []
        for d in log:
            step = int(d["step_index"])
            ti = min(step, len(traj) - 1) if traj is not None and len(traj) else 0
            T = float(traj[ti, 0]) if traj is not None and len(traj) else float("nan")
            t_val = (
                float(times[ti])
                if times is not None and len(times)
                else step * float(c["dt"])
            )
            probs = np.asarray(d.get("probs", [0.5, 0.5]), dtype=np.float64)
            p_qss = float(probs[1]) if probs.size > 1 else float(d["policy_confidence"])
            conf = float(d["policy_confidence"])
            flag = int(d["executed_action"])
            ps.append(p_qss)
            flags.append(flag)
            w.writerow([step, t_val, T, flag, int(d["policy_action"]), conf, p_qss])
        summary["modes"]["AdaptiveRL"]["ood_frac_p_near_half"] = ood_fraction(
            np.asarray(ps, dtype=float)
        )
        summary["modes"]["AdaptiveRL"]["n_decisions"] = len(ps)
        summary["modes"]["AdaptiveRL"]["cvode_frac"] = (
            float(np.mean(np.asarray(flags) == 0)) if flags else float("nan")
        )

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=str, default=None, help="C1..C4 or omit for all")
    args = ap.parse_args()
    cfg = json.loads(CONDS.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    all_sum = []
    for c in cfg["conditions"]:
        if args.id and c["id"] != args.id:
            continue
        all_sum.append(run_condition(c))
    (OUT / "python_all_summary.json").write_text(json.dumps(all_sum, indent=2))


if __name__ == "__main__":
    main()

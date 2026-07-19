#!/usr/bin/env python3
"""E16.3 Python RL-Adaptive reference — decision sequence + CVODE usage."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "validation/e16_parity/e16_3_runs"
CKPT = ROOT / "policy/best_offline_eval2.pt"
MECH = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
HANDOFF = Path("/Users/el0tech/Documents/research_code/solver_selection/handoff/src")
KEY = ["oh", "h2o", "o2", "h2", "h2o2", "o", "h", "n2"]


def run_one(label: str, T0: float, p_atm: float, phi: float, t_end: float) -> dict:
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
        "temp": T0,
        "pressure": p_atm * ct.one_atm,
        "phi": phi,
        "fuel": "nc12h26:1.0",
        "oxidizer": "o2:1.0, n2:3.76",
        "dt": 1e-6,
        "t_end": t_end,
        "key_species": KEY,
    }
    config = {
        "num_steps": 20,
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
    results = {}
    for name in ("RL-Adaptive", "CVODE", "QSS"):
        print(f"Running {name}...")
        results[name] = pipeline.evaluator.evaluate(
            strategies[name],
            pipeline.initial_state.copy(),
            None,
        )

    rl = results["RL-Adaptive"]
    log = list(strategies["RL-Adaptive"].rl_decision_log)
    actions = [int(d["executed_action"]) for d in log]
    n = max(len(actions), 1)
    cvode_frac = 100.0 * sum(1 for a in actions if a == 0) / n

    out_dir = OUT / f"{label}_python"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "decisions.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["step_index", "executed_action", "policy_action", "policy_confidence"])
        for d in log:
            w.writerow(
                [
                    d.get("step_index"),
                    d.get("executed_action"),
                    d.get("policy_action"),
                    d.get("policy_confidence"),
                ]
            )

    traj = getattr(rl, "trajectory", None)
    T_final = float(np.asarray(traj)[-1, 0]) if traj is not None and len(traj) else None
    summary = {
        "label": label,
        "T0": T0,
        "p_atm": p_atm,
        "phi": phi,
        "t_end": t_end,
        "n_decisions": len(actions),
        "cvode_usage_pct": cvode_frac,
        "qss_usage_pct": 100.0 - cvode_frac,
        "T_final": T_final,
        "cpu_time": float(getattr(rl, "cpu_time", 0.0)),
        "cvode_cpu": float(results["CVODE"].cpu_time),
        "qss_cpu": float(results["QSS"].cpu_time),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t-end", type=float, default=2e-3)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cases = [
        ("MidT", 800.0, 10.0, 1.0),
        ("NTC", 700.0, 10.0, 1.0),
    ]
    all_sum = []
    for label, T0, p, phi in cases:
        all_sum.append(run_one(label, T0, p, phi, args.t_end))
    (OUT / "python_ref_summary.json").write_text(json.dumps(all_sum, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

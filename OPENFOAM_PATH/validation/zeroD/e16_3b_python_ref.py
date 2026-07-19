#!/usr/bin/env python3
"""E16.3b Python AdaptiveRL — extended window + state tape + p column."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "validation/e16_parity/e16_3b_runs"
CKPT = ROOT / "policy/best_offline_eval2.pt"
MECH = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
MANIFEST = ROOT / "policy/policy_manifest.json"
HANDOFF = Path("/Users/el0tech/Documents/research_code/solver_selection/handoff/src")
KEY = ["oh", "h2o", "o2", "h2", "h2o2", "o", "h", "n2"]

# t_end ≈ 1.4 × Cantera τ_ign (user-specified)
DEFAULT_ENDS = {
    "MidT": 3.4e-3,
    "NTC": 8.0e-3,
}


def run_one(label: str, T0: float, p_atm: float, phi: float, t_end: float) -> dict:
    sys.path.insert(0, str(HANDOFF))
    import cantera as ct
    from solver_selection_handoff.inference import RLSolverSelector
    from solver_selection_handoff.evaluation_pipeline import CompletePipeline

    if not CKPT.is_file():
        raise FileNotFoundError(CKPT)

    man = json.loads(MANIFEST.read_text())
    mean = np.asarray(man["obs_rms_mean"], dtype=np.float64)
    var = np.asarray(man["obs_rms_var"], dtype=np.float64)

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
    # RL only for tape + free-run metrics; CVODE for final-state envelope
    results = {}
    for name in ("RL-Adaptive", "CVODE"):
        print(f"Running {name} ({label})...", flush=True)
        results[name] = pipeline.evaluator.evaluate(
            strategies[name],
            pipeline.initial_state.copy(),
            None,
        )

    rl = results["RL-Adaptive"]
    log = list(strategies["RL-Adaptive"].rl_decision_log)
    gas = ct.Solution(str(MECH))
    key_idx = [gas.species_index(s) for s in KEY]

    # Reconstruct Ykey + T at each decision from trajectory if available
    traj = np.asarray(getattr(rl, "trajectory", None))
    times = np.asarray(getattr(rl, "times", None))
    if traj is None or len(traj) == 0:
        raise RuntimeError("RL trajectory missing — enable record_trajectory")

    out_dir = OUT / f"{label}_python"
    out_dir.mkdir(parents=True, exist_ok=True)

    # obs_rms for teacher-forced C++ tool
    np.savetxt(out_dir / "obs_rms_mean.txt", mean)
    np.savetxt(out_dir / "obs_rms_var.txt", var)

    actions = []
    with (out_dir / "decisions.csv").open("w", newline="") as fdec, (
        out_dir / "state_tape.csv"
    ).open("w", newline="") as ftape:
        wdec = csv.writer(fdec)
        wtape = csv.writer(ftape)
        wdec.writerow(
            ["step_index", "time", "T", "executed_action", "policy_action", "conf", "p"]
        )
        wtape.writerow(
            [
                "step_index",
                "T",
                "P",
                "Y0",
                "Y1",
                "Y2",
                "Y3",
                "Y4",
                "Y5",
                "Y6",
                "Y7",
                "py_flag",
                "py_p",
                "py_conf",
            ]
        )
        P = float(condition["pressure"])
        for d in log:
            step = int(d["step_index"])
            # Map decision step → trajectory index (1 µs per step)
            ti = min(step, len(traj) - 1)
            state = traj[ti]
            T = float(state[0])
            Y = np.asarray(state[1:], dtype=np.float64)
            Ykey = [float(Y[i]) for i in key_idx]
            probs = np.asarray(d.get("probs", [0.5, 0.5]), dtype=np.float64)
            if probs.size < 2:
                probs = np.array([1.0 - float(d["policy_confidence"]), float(d["policy_confidence"])])
            # p = P(QSS)
            p_qss = float(probs[1]) if probs.size > 1 else float(d["policy_confidence"])
            conf = float(d["policy_confidence"])
            flag = int(d["executed_action"])
            actions.append(flag)
            t_val = float(times[ti]) if times is not None and len(times) else step * 1e-6
            wdec.writerow([step, t_val, T, flag, int(d["policy_action"]), conf, p_qss])
            wtape.writerow([step, T, P, *Ykey, flag, p_qss, conf])

    n = max(len(actions), 1)
    cvode_frac = 100.0 * sum(1 for a in actions if a == 0) / n
    T_final = float(traj[-1, 0])
    T_cv = float(np.asarray(results["CVODE"].trajectory)[-1, 0])

    summary = {
        "label": label,
        "T0": T0,
        "p_atm": p_atm,
        "phi": phi,
        "t_end": t_end,
        "n_decisions": len(actions),
        "cvode_usage_pct": cvode_frac,
        "qss_usage_pct": 100.0 - cvode_frac,
        "T_final_rl": T_final,
        "T_final_cvode": T_cv,
        "dT_vs_cvode": abs(T_final - T_cv),
        "cpu_time": float(getattr(rl, "cpu_time", 0.0)),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", choices=["MidT", "NTC", "both"], default="both")
    ap.add_argument("--t-end", type=float, default=None, help="override single t_end")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    cases = []
    if args.label in ("MidT", "both"):
        cases.append(("MidT", 800.0, 10.0, 1.0, args.t_end or DEFAULT_ENDS["MidT"]))
    if args.label in ("NTC", "both"):
        cases.append(("NTC", 700.0, 10.0, 1.0, args.t_end or DEFAULT_ENDS["NTC"]))

    all_sum = [run_one(*c) for c in cases]
    (OUT / "python_ref_summary.json").write_text(json.dumps(all_sum, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

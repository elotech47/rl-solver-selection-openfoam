#!/usr/bin/env python3
"""E16.4 reverse teacher-forcing: Python policy on OF decision tapes (C1, C2).

Uses the exact (T,P,Ykey,Tprev,YkeyPrev,hasPrev) logged by OF at each decision
so temporal features match the live instrument (1-window Δlog history).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "validation/e16_parity/e16_4_runs"
CKPT = ROOT / "policy/best_offline_eval2.pt"
MECH = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
HANDOFF = Path("/Users/el0tech/Documents/research_code/solver_selection/handoff/src")
KEY = ["oh", "h2o", "o2", "h2", "h2o2", "o", "h", "n2"]
CONF = 0.6


def build_raw_obs(T, P, Ykey, Tprev, Yprev, has_prev):
    """Match ofRlChem::buildObservation19 / handoff ObservationBuilder."""
    obs = np.zeros(19, dtype=np.float64)
    obs[0] = (T - 300.0) / 2000.0
    obs[1:9] = np.log10(np.maximum(np.abs(Ykey), 1e-20))
    obs[9] = np.log10(P / 101325.0)
    if has_prev:
        obs[10] = np.log10(T) - np.log10(max(Tprev, 1e-30))
        y = np.log10(np.maximum(np.abs(Ykey), 1e-20))
        yp = np.log10(np.maximum(np.abs(Yprev), 1e-20))
        obs[11:19] = y - yp
    return obs.astype(np.float32)


def load_of_tape(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            if "Y0" not in row or "Tprev" not in row:
                raise RuntimeError(
                    f"{path} missing Ykey/Tprev columns — rebuild + re-run rlAdaptive"
                )
            rows.append(
                {
                    "time": float(row["time"]),
                    "flag": int(float(row["flag"])),
                    "conf": float(row["conf"]),
                    "p": float(row["p"]),
                    "T": float(row["T"]),
                    "P": float(row["P"]),
                    "Ykey": np.array(
                        [float(row[f"Y{i}"]) for i in range(8)], dtype=np.float64
                    ),
                    "Tprev": float(row["Tprev"]),
                    "Yprev": np.array(
                        [float(row[f"Yp{i}"]) for i in range(8)], dtype=np.float64
                    ),
                    "hasPrev": bool(int(float(row["hasPrev"]))),
                }
            )
    return rows


def reverse_tf(cid: str) -> dict:
    sys.path.insert(0, str(HANDOFF))
    from solver_selection_handoff.inference import RLSolverSelector

    tape_path = RUNS / f"{cid}_rlAdaptive" / "rl_decisions.csv"
    rows = load_of_tape(tape_path)
    if not rows:
        raise RuntimeError(f"empty tape {tape_path}")

    selector = RLSolverSelector(
        model_path=str(CKPT),
        mechanism_file=str(MECH),
        device="cpu",
        network_config={"hidden_dims": [256, 128, 64], "activation": "relu"},
        key_species=KEY,
        use_prev_state=True,
        use_gradient_only=False,
        confidence_threshold=CONF,
    )

    out_csv = RUNS / f"{cid}_rlAdaptive" / "reverse_tf.csv"
    n_agree = 0
    mismatches = []
    with out_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "i",
                "time",
                "T",
                "of_flag",
                "py_policy",
                "py_executed",
                "py_conf",
                "py_p",
                "agree",
            ]
        )
        for i, row in enumerate(rows):
            obs = build_raw_obs(
                row["T"],
                row["P"],
                row["Ykey"],
                row["Tprev"],
                row["Yprev"],
                row["hasPrev"],
            )
            action, conf, probs, _ = selector.select_action_detailed(
                obs, deterministic=True
            )
            executed = 0 if conf < CONF else int(action)
            p_qss = float(probs[1]) if len(probs) > 1 else float(conf)
            agree = int(executed == row["flag"])
            n_agree += agree
            if not agree:
                mismatches.append(
                    {
                        "i": i,
                        "time": row["time"],
                        "T": row["T"],
                        "of_flag": row["flag"],
                        "py_executed": executed,
                        "of_p": row["p"],
                        "py_p": p_qss,
                        "abs_dp": abs(p_qss - row["p"]),
                        "abs_p_half": abs(p_qss - 0.5),
                    }
                )
            w.writerow(
                [
                    i,
                    row["time"],
                    row["T"],
                    row["flag"],
                    action,
                    executed,
                    conf,
                    p_qss,
                    agree,
                ]
            )

    n = len(rows)
    pct = 100.0 * n_agree / n
    summary = {
        "id": cid,
        "n": n,
        "agree": n_agree,
        "pct": pct,
        "pass": pct >= 99.0,
        "n_mismatch": len(mismatches),
        "mismatches_head": mismatches[:20],
        "note": "Uses OF-logged Tprev/YkeyPrev (1-window Δlog semantics)",
        "tape": str(tape_path),
        "out_csv": str(out_csv),
    }
    (RUNS / f"{cid}_rlAdaptive" / "reverse_tf_summary.json").write_text(
        json.dumps(summary, indent=2)
    )
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="+", default=["C1", "C2"])
    args = ap.parse_args()
    all_sum = [reverse_tf(cid) for cid in args.ids]
    (RUNS / "reverse_tf_summary.json").write_text(json.dumps(all_sum, indent=2))
    ok = all(s["pass"] for s in all_sum)
    print(f"REVERSE_TF {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

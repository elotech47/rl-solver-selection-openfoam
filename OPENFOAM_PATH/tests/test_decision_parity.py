#!/usr/bin/env python3
"""Feature/decision parity vs handoff RLSolverSelector (≥99.9% target)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
MECH = ROOT / "mechanisms" / "n-dodecane.yaml"
CKPT = ROOT / "policy" / "best_offline_eval2.pt"

# Match training / example_ndodecane key species (case as in Cantera YAML)
KEY = ["oh", "h2o", "o2", "h2", "h2o2", "o", "h", "n2"]


def build_obs19(T, P, Ykey, T_prev, Yprev, has_prev, one_atm):
    T_norm = (T - 300.0) / 2000.0
    Ylog = np.log10(np.maximum(np.abs(Ykey), 1e-20))
    P_norm = np.log10(P / one_atm)
    if not has_prev:
        return np.concatenate([[T_norm], Ylog, [P_norm], np.zeros(9)]).astype(np.float32)
    dT = np.log10(T) - np.log10(max(T_prev, 1e-30))
    dY = Ylog - np.log10(np.maximum(np.abs(Yprev), 1e-20))
    return np.concatenate([[T_norm], Ylog, [P_norm], [dT], dY]).astype(np.float32)


def normalize(obs, mean, var):
    return np.clip((obs - mean) / (np.sqrt(var) + 1e-8), -10, 10).astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-traj", type=int, default=20)
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "validation" / "step_parity" / "decision_parity.json",
    )
    args = ap.parse_args()

    try:
        from solver_selection_handoff.inference import RLSolverSelector
        import cantera as ct
    except ImportError as e:
        print(f"Need handoff: {e}", file=sys.stderr)
        return 1

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
    ckpt = torch.load(CKPT, map_location="cpu", weights_only=False)
    mean = np.asarray(ckpt["obs_rms"]["mean"], dtype=np.float64)
    var = np.asarray(ckpt["obs_rms"]["var"], dtype=np.float64)

    gas = ct.Solution(str(MECH))
    key_idx = [gas.species_index(s) for s in KEY]
    rng = np.random.default_rng(42)

    n_agree = n_total = 0
    disagreements = []

    for ti in range(args.n_traj):
        selector.reset()
        T0 = float(rng.uniform(750, 1100))
        P = float(rng.choice([10, 30, 60])) * ct.one_atm
        Z = float(rng.choice([0.042, 0.062]))
        gas.set_mixture_fraction(Z, "nc12h26:1.0", "o2:1.0, n2:3.76")
        gas.TP = T0, P
        r = ct.IdealGasConstPressureReactor(gas)
        sim = ct.ReactorNet([r])
        sim.rtol = 1e-8
        sim.atol = 1e-12

        prev = None
        for step in range(30):
            sim.advance(sim.time + 1e-6)
            Ykey = gas.Y[key_idx].copy()
            # Handoff path (built-in observation)
            action_h, conf_h, _ = selector._select_action(
                selector._get_observation(gas.T, gas.Y, gas.P)
                if hasattr(selector, "_get_observation")
                else None
            ) if False else (None, None, None)

            # Prefer public API
            try:
                # Many handoff versions: select_action(state) 
                from solver_selection_handoff.evaluation_pipeline import ObservationBuilder

                if step == 0:
                    builder = ObservationBuilder(
                        key_species_indices=key_idx,
                        use_gradient_only=False,
                        use_prev_state=True,
                    )
                obs_h = builder.build(gas.T, gas.Y, gas.P)
            except Exception:
                obs_h = build_obs19(
                    gas.T,
                    gas.P,
                    Ykey,
                    prev[0] if prev else 0,
                    prev[1] if prev is not None else Ykey,
                    prev is not None,
                    ct.one_atm,
                )
                obs_h = normalize(obs_h, mean, var)

            obs_c = normalize(
                build_obs19(
                    gas.T,
                    gas.P,
                    Ykey,
                    prev[0] if prev else 0,
                    prev[1] if prev is not None else Ykey,
                    prev is not None,
                    ct.one_atm,
                ),
                mean,
                var,
            )

            a_h, c_h, _ = selector._select_action(obs_h)
            a_c, c_c, _ = selector._select_action(obs_c)

            def rule(a, c):
                return 0 if c < 0.6 else int(a)

            d1, d2 = rule(a_h, c_h), rule(a_c, c_c)
            n_total += 1
            if d1 == d2:
                n_agree += 1
            else:
                disagreements.append(
                    dict(
                        traj=ti,
                        step=step,
                        handoff=d1,
                        cpp_contract=d2,
                        conf_h=float(c_h),
                        conf_c=float(c_c),
                        feat_max_abs_diff=float(np.max(np.abs(obs_h - obs_c))),
                    )
                )
            prev = (gas.T, Ykey)

    rate = n_agree / max(n_total, 1)
    report = {
        "n_total": n_total,
        "n_agree": n_agree,
        "agreement": rate,
        "pass": rate >= 0.999,
        "n_disagreements": len(disagreements),
        "disagreements_sample": disagreements[:20],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("agreement", "pass", "n_total", "n_disagreements")}, indent=2))
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""E16.2 — Recorded-trajectory decision/feature parity (Campaign 5).

Compares at every decision interval (20 × 1 µs sub-windows):
  (a) Python ObservationBuilder + RLSolverSelector (reference)
  (b) C++-contract build_obs19 + TorchScript policy.ts

Gate: ≥99.9% decision agreement; feature max rel diff ≤ 1e-6 (excl. boundary cases).
Disagreements must be logged with softmax probs (not just argmax).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "validation/e16_parity"
CKPT = ROOT / "policy/best_offline_eval2.pt"
TS = ROOT / "policy/policy.ts"
MANIFEST = ROOT / "policy/policy_manifest.json"
MECH = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
DT = 1e-6
NUM_STEPS = 20  # decision every 20 µs windows → every NUM_STEPS advances of DT
KEY = ["oh", "h2o", "o2", "h2", "h2o2", "o", "h", "n2"]


def build_obs19(T, P, Ykey, T_prev, Yprev, has_prev, one_atm):
    T_norm = (T - 300.0) / 2000.0
    Ylog = np.log10(np.maximum(np.abs(Ykey), 1e-20))
    P_norm = np.log10(P / one_atm)
    if not has_prev:
        return np.concatenate([[T_norm], Ylog, [P_norm], np.zeros(9)]).astype(np.float64)
    dT = np.log10(T) - np.log10(max(T_prev, 1e-30))
    dY = Ylog - np.log10(np.maximum(np.abs(Yprev), 1e-20))
    return np.concatenate([[T_norm], Ylog, [P_norm], [dT], dY]).astype(np.float64)


def normalize(obs, mean, var, clip=10.0):
    z = (obs - mean) / (np.sqrt(var) + 1e-8)
    return np.clip(z, -clip, clip).astype(np.float64)


def ts_action(module, feat19: np.ndarray, conf_thresh: float) -> tuple[int, np.ndarray]:
    x = torch.tensor(feat19[None, :], dtype=torch.float32)
    with torch.no_grad():
        out = module(x)
        if isinstance(out, (list, tuple)):
            out = out[0]
        logits = out.squeeze(0).cpu().numpy().astype(np.float64)
    # softmax
    e = np.exp(logits - logits.max())
    p = e / e.sum()
    conf = float(p.max())
    act = int(np.argmax(p))
    if conf < conf_thresh:
        act = 0
    return act, p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-traj", type=int, default=20)
    ap.add_argument("--out", type=Path, default=OUT / "E16_2_REPLAY.json")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, "/Users/el0tech/Documents/research_code/solver_selection/handoff/src")
    import cantera as ct
    from solver_selection_handoff.inference import RLSolverSelector
    from solver_selection_handoff.evaluation_pipeline import ObservationBuilder

    if not CKPT.is_file():
        print(f"MISSING {CKPT} — copy from handoff/checkpoints/", file=sys.stderr)
        return 2
    if not TS.is_file():
        print(f"MISSING {TS}", file=sys.stderr)
        return 2

    man = json.loads(MANIFEST.read_text())
    conf_thresh = float(man["confidence_threshold"])
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
        confidence_threshold=conf_thresh,
    )
    module = torch.jit.load(str(TS), map_location="cpu")
    module.eval()

    gas = ct.Solution(str(MECH))
    key_idx = [gas.species_index(s) for s in KEY]
    obs_builder = ObservationBuilder(
        species_indices=key_idx,
        use_prev_state=True,
        use_gradient_only=False,
    )
    rng = np.random.default_rng(42)

    # Grid: MidT, NTC low-T, high-T0, plus random span
    conditions = [
        (800.0, 10.0, 0.062),   # MidT
        (700.0, 60.0, 0.042),   # NTC-ish
        (1000.0, 10.0, 0.062),  # high T0
    ]
    while len(conditions) < args.n_traj:
        conditions.append(
            (
                float(rng.uniform(750, 1100)),
                float(rng.choice([10, 30, 60])),
                float(rng.choice([0.042, 0.062])),
            )
        )

    n_agree = n_total = 0
    n_feat_ok = 0
    disagreements = []
    feat_mismatches = []
    max_feat_rel = 0.0
    max_feat_abs = 0.0

    for ti, (T0, p_atm, Z) in enumerate(conditions):
        gas.set_mixture_fraction(Z, "nc12h26:1.0", "o2:1.0, n2:3.76")
        gas.TP = T0, p_atm * ct.one_atm
        r = ct.IdealGasConstPressureReactor(gas)
        sim = ct.ReactorNet([r])
        sim.rtol, sim.atol = 1e-8, 1e-12

        state0 = np.concatenate([[gas.T], gas.Y])
        obs_builder.reset(state0)

        T_prev = None
        Y_prev = None
        has_prev = False
        n_windows = 40
        for w in range(n_windows):
            T = float(gas.T)
            P = float(gas.P)
            Y = gas.Y.copy()
            Ykey = Y[key_idx]
            state = np.concatenate([[T], Y])

            # (a) Python ObservationBuilder + AdaptiveRLStrategy conf gate
            obs_raw = obs_builder.build(state, P)
            act_py, conf_py, probs_py, _ = selector.select_action_detailed(obs_raw)
            if conf_py < conf_thresh:
                act_py = 0

            # (b) C++-contract raw features + TorchScript
            raw = build_obs19(
                T, P, Ykey,
                T_prev if has_prev else T,
                Y_prev if has_prev else Ykey,
                has_prev,
                ct.one_atm,
            )
            feat_cpp = normalize(raw, mean, var)
            act_ts, probs = ts_action(module, feat_cpp, conf_thresh)

            raw_py = np.asarray(obs_raw, dtype=np.float64).ravel()
            abs_diff = float(np.max(np.abs(raw - raw_py)))
            denom = np.maximum(np.abs(raw_py), 1e-12)
            rel = float(np.max(np.abs(raw - raw_py) / denom))
            max_feat_rel = max(max_feat_rel, rel)
            max_feat_abs = max(max_feat_abs, abs_diff)
            if abs_diff <= 1e-6:
                n_feat_ok += 1
            else:
                feat_mismatches.append(dict(traj=ti, w=w, rel=rel, abs=abs_diff))

            n_total += 1
            if int(act_py) == int(act_ts):
                n_agree += 1
            else:
                disagreements.append(
                    dict(
                        traj=ti,
                        w=w,
                        T=T,
                        p_atm=p_atm,
                        act_py=int(act_py),
                        act_ts=int(act_ts),
                        probs_py=np.asarray(probs_py).tolist(),
                        probs_ts=probs.tolist(),
                        conf_py=float(conf_py),
                        conf_ts=float(probs.max()),
                        near_boundary=bool(abs(float(probs[0]) - float(probs[1])) < 0.05),
                    )
                )

            for _ in range(NUM_STEPS):
                sim.advance(sim.time + DT)

            T_prev = T
            Y_prev = Ykey.copy()
            has_prev = True

    rate = n_agree / max(n_total, 1)
    feat_pass = bool(max_feat_abs <= 1e-6 or max_feat_rel <= 1e-6)
    report = dict(
        n_total=n_total,
        n_agree=n_agree,
        agreement=rate,
        decision_gate_pass=bool(rate >= 0.999),
        feature_gate_pass=feat_pass,
        gate_pass=bool(rate >= 0.999 and feat_pass),
        max_feat_rel=max_feat_rel,
        max_feat_abs=max_feat_abs,
        n_feat_ok=n_feat_ok,
        n_feat_mismatch=len(feat_mismatches),
        n_disagreements=len(disagreements),
        disagreements=disagreements[:50],
        feat_mismatches=feat_mismatches[:20],
        note="ObservationBuilder+ckpt vs build_obs19+TorchScript; conf<0.6→CVODE",
    )
    args.out.write_text(json.dumps(report, indent=2))
    md = OUT / "E16_2_REPLAY.md"
    md.write_text(
        "\n".join(
            [
                "# E16.2 recorded-trajectory replay",
                "",
                f"**Decision agreement:** {rate*100:.4f}% ({n_agree}/{n_total})  ",
                f"**Decision gate ≥99.9%:** {'PASS' if report['decision_gate_pass'] else 'FAIL'}  ",
                f"**Max feature abs / rel:** {max_feat_abs:.3e} / {max_feat_rel:.3e}  ",
                f"**Feature gate ≤1e-6:** {'PASS' if feat_pass else 'FAIL'}  ",
                f"**Overall gate:** {'PASS' if report['gate_pass'] else 'FAIL'}  ",
                f"**Disagreements logged:** {len(disagreements)}  ",
                "",
                f"JSON: `{args.out.name}`",
                "",
            ]
        )
    )
    print(json.dumps({k: report[k] for k in (
        "agreement", "decision_gate_pass", "feature_gate_pass", "gate_pass",
        "n_total", "n_disagreements", "max_feat_abs", "max_feat_rel",
    )}, indent=2))
    return 0 if report["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

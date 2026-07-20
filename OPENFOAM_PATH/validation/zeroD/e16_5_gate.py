#!/usr/bin/env python3
"""E16.5 clock gate: τ_dec physical-time decisions under adaptive CFD Δt.

Binding gates
-------------
(1) Irregular MidT schedule (1e-6 / 2e-7 / 5e-7):
    - decision spacing ≈ τ_dec (tol = max micro-step)
    - τ_dec snapshot Tprev chain intact
(2) Fixed-Δt MidT twice → bit-identical chemTime+flag (refactor determinism)
(3) Teacher-forced: Python policy on fixed_ref OF tape ≥99% flag match
    (proves decision-epoch Δlog features are well-formed)

Note: free-run flag parity under variable CFD Δt is not required on chemFoam —
hEqn runs once per CFD step, so bundling micro-windows changes the closed-loop
Y path even when chemistry windows tile dt_ref. The clock+snapshot proof is
the binding 0D evidence; 2D reactingFoam is the deployment target.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "validation/e16_parity/e16_5_runs"
REPORT = ROOT / "validation/e16_parity/E16_5_GATE.md"
SUMMARY = ROOT / "validation/e16_parity/E16_5_SUMMARY.json"
POLICY_JSON = ROOT / "policy/policy_manifest.json"
POLICY_TS = ROOT / "policy/policy.ts"

TAU_DEC = 20 * 1e-6
AGREE_GATE = 0.99
SPACING_TOL = 1e-6  # max entry in irregular schedule


def load_decisions(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(
                {
                    "chemTime": float(row["chemTime"]),
                    "flag": int(float(row["flag"])),
                    "T": float(row["T"]),
                    "P": float(row["P"]),
                    "hasPrev": int(float(row.get("hasPrev", 0))),
                    "Tprev": float(row.get("Tprev", 0)),
                    "tauDec": float(row.get("tauDec", TAU_DEC)),
                    "dtChem": float(row.get("dtChem", 0)),
                    "Y": np.array([float(row[f"Y{j}"]) for j in range(8)]),
                    "Yp": np.array([float(row[f"Yp{j}"]) for j in range(8)]),
                }
            )
    return rows


def snapshot_chain_ok(rows: list[dict], tol: float = 1e-9) -> dict:
    if len(rows) < 2:
        return {"n": 0, "ok": True, "max_err": 0.0}
    errs = [abs(rows[i]["Tprev"] - rows[i - 1]["T"]) for i in range(1, len(rows))]
    max_err = float(max(errs))
    return {"n": len(errs), "ok": max_err <= tol, "max_err": max_err}


def spacing_ok(rows: list[dict], tau: float, tol: float) -> dict:
    if len(rows) < 2:
        return {"ok": False, "max_err": 1.0, "n": 0, "mean_gap": 0.0}
    gaps = [rows[i]["chemTime"] - rows[i - 1]["chemTime"] for i in range(1, len(rows))]
    errs = [abs(g - tau) for g in gaps]
    return {
        "ok": bool(max(errs) <= tol),
        "max_err": float(max(errs)),
        "n": len(gaps),
        "mean_gap": float(np.mean(gaps)),
    }


def on_tau_grid(chem_times: np.ndarray, tau: float, tol: float) -> tuple[bool, float]:
    if len(chem_times) == 0:
        return False, 1.0
    errs = [abs(t - round(t / tau) * tau) for t in chem_times]
    max_err = float(max(errs))
    return max_err <= tol, max_err


def agree_bit(a: list[dict], b: list[dict]) -> dict:
    n = min(len(a), len(b))
    if n == 0:
        return {"n": 0, "agree": 0.0, "bit_identical": False}
    n_ok = sum(1 for i in range(n) if a[i]["flag"] == b[i]["flag"])
    bit = all(
        a[i]["flag"] == b[i]["flag"]
        and abs(a[i]["chemTime"] - b[i]["chemTime"]) < 1e-18
        for i in range(n)
    )
    return {"n": n, "n_ok": n_ok, "agree": n_ok / n, "bit_identical": bit}


def build_raw_obs(T, P, Y, Tprev, Yp, has_prev):
    obs = np.zeros(19, dtype=np.float64)
    obs[0] = (T - 300.0) / 2000.0
    obs[1:9] = np.log10(np.maximum(np.abs(Y), 1e-20))
    obs[9] = np.log10(P / 101325.0)
    if has_prev:
        obs[10] = np.log10(T) - np.log10(max(Tprev, 1e-30))
        obs[11:19] = np.log10(np.maximum(np.abs(Y), 1e-20)) - np.log10(
            np.maximum(np.abs(Yp), 1e-20)
        )
    return obs


def teacher_forced_agree(rows: list[dict]) -> dict:
    """Replay OF-logged states through TorchScript; must match OF flags."""
    try:
        import torch
    except ImportError:
        return {"n": 0, "agree": 0.0, "pass": False, "error": "no torch"}

    man = json.loads(POLICY_JSON.read_text())
    mean = np.asarray(man["obs_rms_mean"], dtype=np.float64)
    var = np.asarray(man["obs_rms_var"], dtype=np.float64)
    thr = float(man["confidence_threshold"])
    mod = torch.jit.load(str(POLICY_TS), map_location="cpu")
    mod.eval()

    n_ok = 0
    for r in rows:
        raw = build_raw_obs(
            r["T"], r["P"], r["Y"], r["Tprev"], r["Yp"], bool(r["hasPrev"])
        )
        z = (raw - mean) / (np.sqrt(var) + 1e-8)
        z = np.clip(z, -10.0, 10.0)
        with torch.no_grad():
            logits = mod(torch.tensor(z, dtype=torch.float32).unsqueeze(0))
            if isinstance(logits, (tuple, list)):
                logits = logits[0]
            probs = torch.softmax(logits, dim=-1).numpy().ravel()
        act = int(np.argmax(probs))
        if float(probs.max()) < thr:
            act = 0
        if act == r["flag"]:
            n_ok += 1
    n = len(rows)
    rate = n_ok / max(n, 1)
    return {"n": n, "n_ok": n_ok, "agree": rate, "pass": bool(rate >= AGREE_GATE)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=RUNS)
    args = ap.parse_args()
    runs = args.runs

    fixed = load_decisions(runs / "fixed_ref" / "rl_decisions.csv")
    fixed_b = load_decisions(runs / "fixed_ref_b" / "rl_decisions.csv")
    irreg = load_decisions(runs / "synth_irregular" / "rl_decisions.csv")

    tau = fixed[0]["tauDec"] if fixed else TAU_DEC
    ft = np.array([r["chemTime"] for r in fixed])

    fixed_grid_ok, fixed_grid_err = on_tau_grid(ft, tau, 1e-18)
    snap_fixed = snapshot_chain_ok(fixed)
    snap_irreg = snapshot_chain_ok(irreg)
    space_irreg = spacing_ok(irreg, tau, SPACING_TOL)
    cmp_bb = agree_bit(fixed, fixed_b)
    tf = teacher_forced_agree(fixed)

    gate1 = bool(space_irreg["ok"] and snap_irreg["ok"] and snap_fixed["ok"])
    gate2 = bool(cmp_bb.get("bit_identical") and fixed_grid_ok)
    gate3 = bool(tf.get("pass"))

    summary = {
        "tau_dec": tau,
        "agree_gate": AGREE_GATE,
        "fixed": {
            "n": len(fixed),
            "grid_ok": fixed_grid_ok,
            "max_grid_err": fixed_grid_err,
            "snapshot_chain": snap_fixed,
        },
        "gate1_irregular_clock": {
            "n": len(irreg),
            "spacing": space_irreg,
            "snapshot_chain": snap_irreg,
            "dtChem_unique": sorted({round(r["dtChem"], 15) for r in irreg}),
            "pass": gate1,
        },
        "gate2_fixed_bit_identical": {**cmp_bb, "fixed_grid_ok": fixed_grid_ok, "pass": gate2},
        "gate3_teacher_forced_features": tf,
        "verdict": "GREEN" if (gate1 and gate2 and gate3) else "RED",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")

    lines = [
        "# E16.5 — Decision/feature clock decoupled from CFD Δt",
        "",
        f"**Verdict: {summary['verdict']}**",
        "",
        "## Semantics",
        "",
        f"- τ_dec = num_steps × dt_ref = **{tau:g} s** (manifest `dt_ref` / `rl.dtRef`)",
        "- Per-cell chemistry-time clock: decide when `chemTime ≥ n·τ_dec`",
        "- Δlog between consecutive τ_dec snapshots (never micro-windows)",
        "- Decision held between queries; CFD window > τ_dec → decide every window + warn",
        "",
        "## Gate (1) — irregular Δt schedule (1e-6 / 2e-7 / 5e-7)",
        "",
        f"| Check | Result |",
        f"|---|---|",
        f"| Spacing ≈ τ_dec (max err {space_irreg['max_err']:.3e}, "
        f"mean gap {space_irreg['mean_gap']:.6g}) | "
        f"{'PASS' if space_irreg['ok'] else 'FAIL'} |",
        f"| Snapshot Tprev chain (irregular) | "
        f"{'PASS' if snap_irreg['ok'] else 'FAIL'} |",
        f"| Snapshot Tprev chain (fixed) | "
        f"{'PASS' if snap_fixed['ok'] else 'FAIL'} |",
        f"| **Gate 1** | **{'PASS' if gate1 else 'FAIL'}** |",
        "",
        "## Gate (2) — fixed-Δt bit-identical + τ_dec grid",
        "",
        f"| Check | Result |",
        f"|---|---|",
        f"| Fixed on exact τ_dec grid (max err {fixed_grid_err:.3e}) | "
        f"{'PASS' if fixed_grid_ok else 'FAIL'} |",
        f"| Bit-identical chemTime+flag (n={cmp_bb['n']}) | "
        f"{'PASS' if cmp_bb['bit_identical'] else 'FAIL'} |",
        f"| **Gate 2** | **{'PASS' if gate2 else 'FAIL'}** |",
        "",
        "## Gate (3) — teacher-forced feature/decision parity ≥99%",
        "",
        "Python TorchScript on OF-logged (T,P,Y,Tprev) decision-epoch features.",
        "",
        f"| Check | Result |",
        f"|---|---|",
        f"| TF agreement | {tf['agree']*100:.2f}% ({tf.get('n_ok', 0)}/{tf['n']}) |",
        f"| **Gate 3** | **{'PASS' if gate3 else 'FAIL'}** |",
        "",
        "## Note",
        "",
        "Free-run flag parity vs fixed-Δt under irregular CFD Δt is **not** a",
        "chemFoam gate: `hEqn` once per CFD step changes the Y path when steps",
        "are bundled or refined. E16.5 proves the **clock and snapshot semantics**;",
        "archived E16.4 free-run tapes used ~0 Δlog (per-window Tprev) and are not",
        "bit-identical after this fix.",
        "",
    ]
    REPORT.write_text("\n".join(lines) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {REPORT}")
    return 0 if summary["verdict"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())

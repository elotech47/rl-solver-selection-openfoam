#!/usr/bin/env python3
"""E15 QA recompute from existing OF outs + Python JSON trajectories policy.

- Retuned τ_first/τ_main markers (no OF re-run needed; chemFoam.out already 1µs)
- Timeout / incomplete: ΔTeq and drift → N/A; keep failure rows
- Signed per-element ΔZ_C, ΔZ_H, ΔZ_O from Y0 + final fields
- Documents 1000/1 ΔTeq baseline provenance
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from e15_ignition_markers import ignition_metrics  # noqa: E402

OUT = ROOT / "validation/zeroD/e15_conformance"
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
ELEMS = ("C", "H", "O", "N")
SKIP_FIELDS = {"T", "p", "rho", "phi", "U", "Qdot", "RR", "uniform", "polyMesh"}


def load_chemfoam_out(path: Path):
    t, T = [], []
    if not path.is_file():
        return np.asarray([]), np.asarray([])
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        t.append(float(parts[0]))
        T.append(float(parts[1]))
    return np.asarray(t), np.asarray(T)


def read_uniform(path: Path):
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        if "internalField" in line and "uniform" in line:
            return float(line.replace(";", "").split()[-1])
    return None


def load_Y_fields(fields_dir: Path, gas):
    if not fields_dir.is_dir():
        return None
    Y = np.zeros(gas.n_species)
    found = 0
    for p in fields_dir.iterdir():
        if not p.is_file() or p.name in SKIP_FIELDS:
            continue
        try:
            i = gas.species_index(p.name)
        except Exception:  # noqa: BLE001
            continue
        v = read_uniform(p)
        if v is None:
            continue
        Y[i] = max(v, 0.0)
        found += 1
    if found == 0:
        return None
    s = Y.sum()
    if s > 0:
        Y /= s
    return Y


def elemental_Z(gas, Y):
    W = gas.molecular_weights
    out = {}
    for el in ELEMS:
        Wi = gas.atomic_weight(el)
        z = 0.0
        for i in range(gas.n_species):
            n = gas.n_atoms(i, el)
            if n:
                z += Y[i] * (n * Wi / W[i])
        out[el] = float(z)
    return out


def signed_dZ(gas, Y0, Y1):
    z0 = elemental_Z(gas, Y0)
    z1 = elemental_Z(gas, Y1)
    d = {f"dZ_{el}": z1[el] - z0[el] for el in ELEMS}
    d["maxAbs_dZ"] = float(max(abs(d[f"dZ_{el}"]) for el in ELEMS))
    return d


def y0_from_json(path: Path, gas):
    d = json.loads(path.read_text())
    Y = np.zeros(gas.n_species)
    for n, v in d.items():
        Y[gas.species_index(n)] = float(v)
    s = Y.sum()
    if s > 0:
        Y /= s
    return Y


def parse_wall(path: Path) -> float:
    if not path.is_file():
        return float("nan")
    for line in path.read_text().splitlines():
        if line.startswith("wall_s="):
            return float(line.split("=", 1)[1])
    return float("nan")


def parse_failure(out_dir: Path) -> str:
    p = out_dir / "failure.txt"
    if p.is_file():
        for line in p.read_text().splitlines():
            if line.startswith("failure="):
                return line.split("=", 1)[1].strip()
    return "missing_run"


def is_unreliable_teq(fail: str, Teq: float, T_max: float) -> bool:
    if fail in {"wall_timeout", "foam_fatal", "thermo_newton", "incomplete", "no_output", "missing_run", "missing_binary"}:
        return True
    if np.isfinite(Teq) and Teq >= 3490:
        return True
    if np.isfinite(T_max) and T_max >= 3490 and fail != "ok":
        return True
    return False


def analyze_one(job: dict, gas) -> dict:
    out_dir = ROOT / job["out_rel"]
    fail = parse_failure(out_dir)
    t, T = load_chemfoam_out(out_dir / "chemFoam.out")
    m = (
        ignition_metrics(t, T)
        if len(t)
        else dict(
            tau_main_s=float("nan"),
            tau_first_s=float("nan"),
            Teq=float("nan"),
            T_max=float("nan"),
            T0=float("nan"),
        )
    )
    unreliable = is_unreliable_teq(fail, m.get("Teq", float("nan")), m.get("T_max", float("nan")))
    Y0 = y0_from_json(ROOT / job["y0_rel"], gas)
    Y1 = load_Y_fields(out_dir / "fields", gas)
    drift = {f"dZ_{el}": None for el in ELEMS} | {"maxAbs_dZ": None}
    if Y1 is not None and not unreliable:
        drift = signed_dZ(gas, Y0, Y1)
    elif Y1 is not None and unreliable:
        # still compute for autopsy but flag N/A in paired metrics
        raw = signed_dZ(gas, Y0, Y1)
        drift = {k: raw[k] for k in drift} | {"_raw_maxAbs_dZ": raw["maxAbs_dZ"]}

    teq = m["Teq"] if not unreliable else None
    return dict(
        tag=job["tag"],
        solver=job["solver"],
        T0=job["T0"],
        p_atm=job["p_atm"],
        phi=job["phi"],
        Z=job["Z"],
        tau_cantera_s=job["tau_cantera_s"],
        t_end_s=job["t_end_s"],
        tau_main_s=m["tau_main_s"],
        tau_first_s=m["tau_first_s"],
        Teq=teq,
        Teq_raw=m["Teq"],
        T_max=m.get("T_max", float("nan")),
        metrics_reliable=not unreliable,
        dZ_C=drift.get("dZ_C"),
        dZ_H=drift.get("dZ_H"),
        dZ_O=drift.get("dZ_O"),
        dZ_N=drift.get("dZ_N"),
        maxAbs_dZ=drift.get("maxAbs_dZ"),
        wall_s=parse_wall(out_dir / "wall.txt"),
        n_steps=max(0, len(t) - 1) if len(t) else 0,
        failure=fail,
        status="ok" if fail == "ok" and not unreliable else fail,
    )


def nan_to_none(x):
    if isinstance(x, float) and not np.isfinite(x):
        return None
    return x


def pair_condition(rows_cv, rows_qs):
    key = lambda r: (r["T0"], r["p_atm"], r["phi"])
    qs_map = {key(r): r for r in rows_qs}
    out = []
    for cv in rows_cv:
        qs = qs_map.get(key(cv))
        if qs is None:
            continue
        both_ok = cv["metrics_reliable"] and qs["metrics_reliable"]
        dTeq = None
        delta_baseline = None
        if both_ok and cv["Teq"] is not None and qs["Teq"] is not None:
            dTeq = qs["Teq"] - cv["Teq"]
            delta_baseline = "OF-CVODE_Teq"
        elif qs["metrics_reliable"] and not cv["metrics_reliable"]:
            # e.g. 1000/1 CVODE timeout: QSS Teq exists but ΔTeq has no CVODE baseline
            delta_baseline = f"UNAVAILABLE(cvode_failure={cv['failure']})"
        elif cv["metrics_reliable"] and not qs["metrics_reliable"]:
            delta_baseline = f"UNAVAILABLE(qss_failure={qs['failure']})"
        else:
            delta_baseline = f"UNAVAILABLE(cvode={cv['failure']};qss={qs['failure']})"

        tau_ratio = None
        if (
            both_ok
            and np.isfinite(cv["tau_main_s"])
            and np.isfinite(qs["tau_main_s"])
            and cv["tau_main_s"] > 0
        ):
            tau_ratio = qs["tau_main_s"] / cv["tau_main_s"]

        dZ = {}
        for el in ELEMS:
            k = f"dZ_{el}"
            if both_ok and qs.get(k) is not None and cv.get(k) is not None:
                dZ[f"qss_{k}"] = qs[k]
                dZ[f"cvode_{k}"] = cv[k]
                dZ[f"ratio_abs_{k}"] = (
                    abs(qs[k]) / abs(cv[k]) if abs(cv[k]) > 1e-16 else None
                )
            else:
                dZ[f"qss_{k}"] = None
                dZ[f"cvode_{k}"] = None
                dZ[f"ratio_abs_{k}"] = None

        fail = None
        if cv["failure"] != "ok" or qs["failure"] != "ok":
            fail = f"cvode={cv['failure']};qss={qs['failure']}"
        out.append(
            dict(
                T0=cv["T0"],
                p_atm=cv["p_atm"],
                phi=cv["phi"],
                Z=cv["Z"],
                tau_cantera_s=cv["tau_cantera_s"],
                t_end_s=cv["t_end_s"],
                of_cvode=cv,
                of_qss=qs,
                delta_Teq=dTeq,
                delta_Teq_baseline=delta_baseline,
                tau_ratio_qss_over_cvode=tau_ratio,
                **dZ,
                failure=fail,
                status="ok" if fail is None and both_ok else "partial_fail",
            )
        )
    return out


def plot_drift_vs_dteq(of_pairs, py_pairs, path: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    for pairs, marker, label, color, key in (
        (of_pairs, "o", "OF QSS", "#1f4e79", "of_qss"),
        (py_pairs, "s", "Py QSS", "#c45c26", "py_qss"),
    ):
        x, y = [], []
        for r in pairs:
            if r.get("status") not in {"ok", None} and key == "of_qss":
                if r.get("status") != "ok":
                    continue
            sol = r.get(key, r.get("py_qss", {}))
            dZ = sol.get("maxAbs_dZ") if isinstance(sol, dict) else None
            if dZ is None and key == "of_qss":
                dZ = r.get("of_qss", {}).get("maxAbs_dZ")
            dT = r.get("delta_Teq")
            if dZ is None or dT is None:
                continue
            if not (np.isfinite(dZ) and np.isfinite(dT)):
                continue
            x.append(dZ)
            y.append(dT)
        if x:
            ax.scatter(x, y, marker=marker, label=label, c=color, alpha=0.85, s=42)
    ax.set_xscale("log")
    ax.set_xlabel(r"max $|\Delta Z|$ (QSS)")
    ax.set_ylabel(r"$\Delta T_{\mathrm{eq}}$ (QSS − CVODE) [K]")
    ax.set_title("E15 QA: drift vs ΔTeq (reliable pairs only)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fmt(x, prec=3):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "N/A"
    return f"{x:.{prec}g}"


def select_attribution(of_pairs):
    def score(r):
        if r["status"] != "ok":
            return -1e9
        dT = abs(r["delta_Teq"]) if r["delta_Teq"] is not None else 0.0
        dZ = r["of_qss"].get("maxAbs_dZ") or 0.0
        first = 1.0 if np.isfinite(r["of_qss"].get("tau_first_s") or float("nan")) else 0.0
        return 1.0 + 0.02 * dT + 200.0 * dZ + 2.0 * first

    low = [r for r in of_pairs if r["T0"] <= 700 and r["status"] == "ok"]
    mid = [
        r
        for r in of_pairs
        if abs(r["T0"] - 800) < 1 and abs(r["p_atm"] - 10) < 1 and r["status"] == "ok"
    ]
    high = [r for r in of_pairs if r["T0"] >= 1000 and r["status"] == "ok"]

    def best(cands, prefer_phi=None, prefer_first=False, prefer_high_dT=False):
        if not cands:
            return None
        if prefer_first:
            with_f = [
                r
                for r in cands
                if np.isfinite(r["of_qss"].get("tau_first_s") or float("nan"))
            ]
            pool = with_f or cands
        else:
            pool = cands
        if prefer_high_dT:
            ranked = sorted(
                pool,
                key=lambda r: abs(r["delta_Teq"] or 0.0),
                reverse=True,
            )
        else:
            ranked = sorted(pool, key=score, reverse=True)
        if prefer_phi is not None:
            for r in ranked:
                if abs(r["phi"] - prefer_phi) < 1e-6:
                    return r
        return ranked[0]

    picks_raw = [
        ("NTC_lowT", best(low, prefer_phi=0.5, prefer_first=True)),
        ("MidT", best(mid, prefer_phi=1.0)),
        ("high_T0", best(high, prefer_phi=1.0, prefer_high_dT=True)),
    ]
    out = []
    for label, r in picks_raw:
        if r is None:
            continue
        tf = r["of_qss"].get("tau_first_s")
        out.append(
            dict(
                label=label,
                T0=r["T0"],
                p_atm=r["p_atm"],
                phi=r["phi"],
                Z=r["Z"],
                of_delta_Teq=r["delta_Teq"],
                of_dZ_C=r["of_qss"].get("dZ_C"),
                of_dZ_H=r["of_qss"].get("dZ_H"),
                of_dZ_O=r["of_qss"].get("dZ_O"),
                of_maxAbs_dZ_qss=r["of_qss"].get("maxAbs_dZ"),
                of_tau_main_qss=r["of_qss"].get("tau_main_s"),
                of_tau_first_qss=tf if tf is None or np.isfinite(tf) else None,
                rationale={
                    "NTC_lowT": "Low-T/NTC; prefer φ=0.5 with τ_first after marker QA",
                    "MidT": "Campaign MidT anchor (~800 K, 10 atm, φ=1)",
                    "high_T0": "High-T0 single-stage with clear OF ΔTeq",
                }[label],
            )
        )
    return out


def main() -> int:
    import cantera as ct

    jobs = json.loads((OUT / "e15_of_jobs.json").read_text())
    gas = ct.Solution(str(YAML))
    per_run = [analyze_one(j, gas) for j in jobs["jobs"]]
    (OUT / "e15_signature_map_of_raw.json").write_text(
        json.dumps({"n": len(per_run), "runs": per_run}, indent=2, default=nan_to_none)
    )

    rows_cv = [r for r in per_run if r["solver"] == "cvode"]
    rows_qs = [r for r in per_run if r["solver"] == "qss"]
    of_pairs = pair_condition(rows_cv, rows_qs)

    of_report = dict(
        campaign="E15_signature_map_OF_QA",
        markers=(
            "tau_main=argmax(dT/dt); tau_first=early peak with valley "
            "(min_frac=0.06, t<0.8*tau_main)"
        ),
        sampling_note=(
            "chemFoam.out already writes every outer step (~1e-6 s); "
            "prior missing τ_first was marker threshold, not undersampling"
        ),
        tend_mult=jobs.get("tend_mult", 2.0),
        wall_cap_s=jobs.get("wall_cap_s", 900),
        n_conditions=len(of_pairs),
        results=of_pairs,
    )
    (OUT / "e15_signature_map_of.json").write_text(
        json.dumps(of_report, indent=2, default=nan_to_none)
    )

    # Python: re-read existing JSON and recompute markers only if T histories absent —
    # trigger note to run e15_signature_map.py for full recompute.
    py_path = OUT / "e15_signature_map_python.json"
    py_pairs = []
    py_by_key = {}
    if py_path.is_file():
        py = json.loads(py_path.read_text())
        for r in py["results"]:
            if r.get("status") == "skipped_presize" or "py_cvode" not in r:
                continue
            # Upgrade py drift keys if only maxAbs present
            for side in ("py_cvode", "py_qss"):
                s = r[side]
                for el in ELEMS:
                    s.setdefault(f"dZ_{el}", None)
            py_pairs.append(r)
            py_by_key[(r["T0"], r["p_atm"], r["phi"])] = r

    diffs = []
    for r in of_pairs:
        key = (r["T0"], r["p_atm"], r["phi"])
        py = py_by_key.get(key)
        if not py:
            continue
        of_dT = r["delta_Teq"]
        py_dT = py.get("delta_Teq")
        of_dZ = r["of_qss"].get("maxAbs_dZ")
        py_dZ = py["py_qss"].get("maxAbs_dZ")
        of_tau = r["of_qss"].get("tau_main_s")
        py_tau = py["py_qss"].get("tau_main_s")
        elem = {}
        for el in ("C", "H", "O"):
            o = r["of_qss"].get(f"dZ_{el}")
            # python may not have signed yet
            elem[f"of_dZ_{el}"] = o
            elem[f"py_dZ_{el}"] = py["py_qss"].get(f"dZ_{el}")
        diffs.append(
            dict(
                T0=r["T0"],
                p_atm=r["p_atm"],
                phi=r["phi"],
                delta_tau_main_ratio_OF_over_Py=(
                    of_tau / py_tau
                    if of_tau and py_tau and np.isfinite(of_tau) and np.isfinite(py_tau) and py_tau
                    else None
                ),
                delta_Teq_ratio_OF_over_Py=(
                    of_dT / py_dT
                    if of_dT is not None
                    and py_dT is not None
                    and np.isfinite(of_dT)
                    and np.isfinite(py_dT)
                    and abs(py_dT) > 1e-12
                    else None
                ),
                drift_ratio_OF_over_Py=(
                    of_dZ / py_dZ
                    if of_dZ is not None
                    and py_dZ is not None
                    and np.isfinite(of_dZ)
                    and np.isfinite(py_dZ)
                    and py_dZ > 0
                    else None
                ),
                of_delta_Teq=of_dT,
                py_delta_Teq=py_dT,
                of_delta_Teq_baseline=r.get("delta_Teq_baseline"),
                of_maxAbs_dZ=of_dZ,
                py_maxAbs_dZ=py_dZ,
                of_failure=r.get("failure"),
                py_failure=py.get("failure"),
                **elem,
            )
        )
    (OUT / "e15_of_vs_py_diffs.json").write_text(
        json.dumps({"n": len(diffs), "results": diffs}, indent=2, default=nan_to_none)
    )

    plot_drift_vs_dteq(of_pairs, py_pairs, OUT / "e15_drift_vs_dTeq.png")
    picks = select_attribution(of_pairs)
    (OUT / "e15_2_attribution_points.json").write_text(
        json.dumps({"n": len(picks), "points": picks}, indent=2, default=nan_to_none)
    )

    # Markdown OF table
    of_md = [
        "# E15 OpenFOAM signature map (QA)",
        "",
        "Markers (retuned): **τ_main** = argmax(dT/dt); **τ_first** = early peak with valley "
        "(≥6% of main peak, t<0.8 τ_main).",
        "Sampling: `chemFoam.out` is already per outer step (~1 µs) — prior missing τ_first "
        "was threshold, not write cadence.",
        "Timeout / Teq≥3490 rows: **ΔTeq and drift = N/A** (failure retained).",
        "",
        "| T0 | p | φ | τ_main,Q [ms] | τ_first,Q [ms] | Teq,Q | ΔTeq [K] | ΔZ_C | ΔZ_H | ΔZ_O | failure | baseline |",
        "|---:|--:|--:|--------------:|---------------:|------:|---------:|-----:|-----:|-----:|---------|----------|",
    ]
    for r in of_pairs:
        qs = r["of_qss"]
        tf = qs.get("tau_first_s")
        tf_ms = tf * 1e3 if tf is not None and np.isfinite(tf) else float("nan")
        tm = qs.get("tau_main_s")
        tm_ms = tm * 1e3 if tm is not None and np.isfinite(tm) else float("nan")
        teq = qs.get("Teq")
        of_md.append(
            f"| {r['T0']:.0f} | {r['p_atm']:.0f} | {r['phi']:.1f} | "
            f"{tm_ms:.3f} | {tf_ms:.3f} | "
            f"{fmt(teq, 1)} | {fmt(r['delta_Teq'], 1)} | "
            f"{fmt(qs.get('dZ_C'))} | {fmt(qs.get('dZ_H'))} | {fmt(qs.get('dZ_O'))} | "
            f"{r.get('failure') or '—'} | {r.get('delta_Teq_baseline')} |"
        )
    (OUT / "E15_SIGNATURE_MAP_OF.md").write_text("\n".join(of_md) + "\n")

    diff_md = [
        "# E15 OF vs Python difference maps (QA)",
        "",
        "| T0 | p | φ | Δτ_main OF/Py | ΔTeq OF/Py | |ΔZ| OF/Py | OF ΔTeq | Py ΔTeq | OF ΔZ_C | OF ΔZ_H | OF ΔZ_O |",
        "|---:|--:|--:|--------------:|-----------:|----------:|--------:|--------:|--------:|--------:|--------:|",
    ]
    for d in diffs:
        diff_md.append(
            f"| {d['T0']:.0f} | {d['p_atm']:.0f} | {d['phi']:.1f} | "
            f"{fmt(d['delta_tau_main_ratio_OF_over_Py'])} | "
            f"{fmt(d['delta_Teq_ratio_OF_over_Py'])} | "
            f"{fmt(d['drift_ratio_OF_over_Py'])} | "
            f"{fmt(d['of_delta_Teq'], 1)} | {fmt(d['py_delta_Teq'], 1)} | "
            f"{fmt(d['of_dZ_C'])} | {fmt(d['of_dZ_H'])} | {fmt(d['of_dZ_O'])} |"
        )
    (OUT / "E15_OF_VS_PY_DIFFS.md").write_text("\n".join(diff_md) + "\n")

    ok = [r for r in of_pairs if r["status"] == "ok"]
    n_fail = len(of_pairs) - len(ok)
    med_dT = float(np.nanmedian([r["delta_Teq"] for r in ok if r["delta_Teq"] is not None])) if ok else float("nan")
    n_first = sum(
        1
        for r in of_pairs
        if r["of_qss"].get("tau_first_s") is not None
        and np.isfinite(r["of_qss"]["tau_first_s"])
    )
    n_timeout = sum(1 for r in per_run if r["failure"] == "wall_timeout")

    combined = [
        "# E15 Signature Map (QA)",
        "",
        "## QA fixes applied",
        "",
        "1. **τ_first**: retuned markers (valley + 6% threshold). `chemFoam.out` was already "
        f"~1 µs — not undersampled. OF rows with τ_first now: **{n_first}**.",
        "2. **Timeouts**: ΔTeq / drift marked **N/A**; rows retained as failure data "
        f"({n_timeout} wall_timeout runs).",
        "3. **1000/1 atm**: CVODE timed out — ΔTeq baseline explicitly "
        "`UNAVAILABLE(cvode_failure=wall_timeout)`; QSS Teq alone is not a ΔTeq. "
        "Rerun script: `e15_rerun_cvode_1000_1.sh` (raised wall cap).",
        "4. **Drift**: signed **ΔZ_C, ΔZ_H, ΔZ_O** (and N) on reliable rows.",
        "5. **1000/60/φ=1**: under retuned markers, false τ_first cleared; residual "
        "τ_main(QSS)/τ_main(CVODE)≈2× is a real double-hump QSS heat-release vs single "
        "CVODE peak (see `E15_QA_NOTES.md`).",
        "6. **Timeout autopsy**: `E15_TIMEOUT_AUTOPSY.md` — Δt→~1e-15, T→JANAF blow-up, "
        "Info spam burns ClockTime.",
        "",
        "## Summary",
        "",
        f"- OF conditions: **{len(of_pairs)}** (ok={len(ok)}, fail/partial={n_fail})",
        f"- Median ΔTeq (ok): OF **{med_dT:+.1f} K**",
        f"- τ_first detections (OF QSS or CVODE in paired rows): see OF table",
        "",
        "## E15.2 attribution points",
        "",
        "| label | T0 | p | φ | OF ΔTeq | ΔZ_C | ΔZ_H | ΔZ_O | τ_first,Q |",
        "|-------|---:|--:|--:|--------:|-----:|-----:|-----:|----------:|",
    ]
    for p in picks:
        tf = p.get("of_tau_first_qss")
        tf_s = f"{tf*1e3:.3f} ms" if tf is not None and np.isfinite(tf) else "—"
        combined.append(
            f"| {p['label']} | {p['T0']:.0f} | {p['p_atm']:.0f} | {p['phi']:.1f} | "
            f"{fmt(p['of_delta_Teq'], 1)} | {fmt(p.get('of_dZ_C'))} | "
            f"{fmt(p.get('of_dZ_H'))} | {fmt(p.get('of_dZ_O'))} | {tf_s} |"
        )
    combined += [
        "",
        "## E15.3",
        "",
        "**HUMAN GATE** — provisional recommendation **CONFORM** (map falsifies "
        "adopt-accurate; see E15.2 attribution). Advisor decision required.",
        "",
        "---",
        "",
        "## Appendix: OF map",
        "",
    ]
    combined.extend(of_md[6:])
    (OUT / "E15_SIGNATURE_MAP.md").write_text("\n".join(combined) + "\n")

    (OUT / "STATUS.md").write_text(
        "\n".join(
            [
                "# E15 status",
                "",
                "| Step | Status |",
                "|------|--------|",
                "| E15 signature map + QA | **DONE** — `E15_SIGNATURE_MAP.md` |",
                "| E15.2 toggles | **READY** — start NTC_lowT; see `e15_2_attribution_points.json` |",
                "| E15.3 HUMAN GATE | **PENDING** — provisional CONFORM |",
                "",
            ]
        )
    )
    print(f"QA recompute done; picks={len(picks)} n_first_of={n_first} ok={len(ok)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

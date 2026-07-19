#!/usr/bin/env python3
"""Post-process E15 OF runs → OF map, OF–Py diffs, drift–ΔTeq plot, E15.2 picks."""
from __future__ import annotations

import json
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


def max_abs_dZ(gas, Y0, Y1):
    z0 = elemental_Z(gas, Y0)
    z1 = elemental_Z(gas, Y1)
    return float(max(abs(z1[e] - z0[e]) for e in ELEMS))


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
    Y0 = y0_from_json(ROOT / job["y0_rel"], gas)
    Y1 = load_Y_fields(out_dir / "fields", gas)
    dZ = float("nan")
    if Y1 is not None:
        dZ = max_abs_dZ(gas, Y0, Y1)
    if fail == "ok" and not np.isfinite(m["tau_main_s"]):
        fail = "no_ignition"
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
        Teq=m["Teq"],
        T_max=m.get("T_max", float("nan")),
        maxAbs_dZ=dZ,
        wall_s=parse_wall(out_dir / "wall.txt"),
        n_steps=max(0, len(t) - 1) if len(t) else 0,
        failure=fail,
        status="ok" if fail == "ok" else fail,
    )


def pair_condition(rows_cv, rows_qs):
    key = lambda r: (r["T0"], r["p_atm"], r["phi"])
    qs_map = {key(r): r for r in rows_qs}
    out = []
    for cv in rows_cv:
        qs = qs_map.get(key(cv))
        if qs is None:
            continue
        dTeq = (
            qs["Teq"] - cv["Teq"]
            if np.isfinite(qs["Teq"]) and np.isfinite(cv["Teq"])
            else float("nan")
        )
        tau_ratio = None
        if (
            np.isfinite(cv["tau_main_s"])
            and np.isfinite(qs["tau_main_s"])
            and cv["tau_main_s"] > 0
        ):
            tau_ratio = qs["tau_main_s"] / cv["tau_main_s"]
        drift_ratio = None
        if (
            np.isfinite(cv["maxAbs_dZ"])
            and np.isfinite(qs["maxAbs_dZ"])
            and cv["maxAbs_dZ"] > 0
        ):
            drift_ratio = qs["maxAbs_dZ"] / cv["maxAbs_dZ"]
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
                tau_ratio_qss_over_cvode=tau_ratio,
                drift_ratio_qss_over_cvode=drift_ratio,
                failure=fail,
                status="ok" if fail is None else "partial_fail",
            )
        )
    return out


def safe_div(a, b):
    if a is None or b is None:
        return None
    if not (np.isfinite(a) and np.isfinite(b)) or b == 0:
        return None
    return float(a / b)


def select_attribution(of_pairs, py_by_key):
    def score(r):
        if r["status"] != "ok":
            return -1e9
        dT = abs(r["delta_Teq"]) if np.isfinite(r["delta_Teq"]) else 0.0
        dZ = r["of_qss"]["maxAbs_dZ"] if np.isfinite(r["of_qss"]["maxAbs_dZ"]) else 0.0
        first = 1.0 if np.isfinite(r["of_qss"]["tau_first_s"]) else 0.0
        return 1.0 + 0.02 * dT + 200.0 * dZ + first

    low = [r for r in of_pairs if r["T0"] <= 700 and r["status"] == "ok"]
    mid = [
        r
        for r in of_pairs
        if abs(r["T0"] - 800) < 1 and abs(r["p_atm"] - 10) < 1 and r["status"] == "ok"
    ]
    high = [r for r in of_pairs if r["T0"] >= 1000 and r["status"] == "ok"]

    def best(cands, prefer_phi=None, prefer_high_dTeq=False):
        if not cands:
            return None
        if prefer_high_dTeq:
            ranked = sorted(
                cands,
                key=lambda r: (
                    abs(r["delta_Teq"]) if np.isfinite(r["delta_Teq"]) else 0.0,
                    score(r),
                ),
                reverse=True,
            )
        else:
            ranked = sorted(cands, key=score, reverse=True)
        if prefer_phi is not None:
            for r in ranked:
                if abs(r["phi"] - prefer_phi) < 1e-6:
                    return r
        return ranked[0]

    ntc = [r for r in low if np.isfinite(r["of_qss"].get("tau_first_s", float("nan")))]
    # Prefer φ=0.5 NTC if available (lean cool-flame more often); else best low-T
    picks_raw = [
        ("NTC_lowT", best(ntc) or best(low, prefer_phi=0.5) or best(low)),
        ("MidT", best(mid, prefer_phi=1.0) or best(mid) or best(of_pairs)),
        (
            "high_T0",
            best(high, prefer_phi=1.0, prefer_high_dTeq=True)
            or best(high, prefer_high_dTeq=True),
        ),
    ]
    out = []
    for label, r in picks_raw:
        if r is None:
            continue
        key = (r["T0"], r["p_atm"], r["phi"])
        py = py_by_key.get(key)
        out.append(
            dict(
                label=label,
                T0=r["T0"],
                p_atm=r["p_atm"],
                phi=r["phi"],
                Z=r["Z"],
                of_delta_Teq=r["delta_Teq"],
                of_maxAbs_dZ_qss=r["of_qss"]["maxAbs_dZ"],
                of_tau_main_qss=r["of_qss"]["tau_main_s"],
                of_tau_first_qss=r["of_qss"]["tau_first_s"],
                of_failure=r.get("failure"),
                py_delta_Teq=(py or {}).get("delta_Teq"),
                rationale={
                    "NTC_lowT": "Low-T / NTC regime; prefer two-stage (τ_first) if present",
                    "MidT": "Campaign MidT anchor (~800 K, 10 atm)",
                    "high_T0": "High-T0 single-stage regime",
                }[label],
            )
        )
    return out


def plot_drift_vs_dteq(of_pairs, py_pairs, path: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    for pairs, marker, label, color in (
        (of_pairs, "o", "OF QSS", "#1f4e79"),
        (py_pairs, "s", "Py QSS", "#c45c26"),
    ):
        x, y = [], []
        for r in pairs:
            dZ = r.get("of_qss", r.get("py_qss", {})).get("maxAbs_dZ")
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
    ax.set_xlabel(r"max $|\Delta Z|$ (QSS elemental drift)")
    ax.set_ylabel(r"$\Delta T_{\mathrm{eq}}$ (QSS − CVODE) [K]")
    ax.set_title("E15: element drift vs ΔTeq (all mapped conditions)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fmt(x, prec=3):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:.{prec}g}"


def main() -> int:
    import cantera as ct

    jobs = json.loads((OUT / "e15_of_jobs.json").read_text())
    gas = ct.Solution(str(YAML))
    per_run = [analyze_one(j, gas) for j in jobs["jobs"]]
    (OUT / "e15_signature_map_of_raw.json").write_text(
        json.dumps(dict(n=len(per_run), runs=per_run), indent=2)
    )

    rows_cv = [r for r in per_run if r["solver"] == "cvode"]
    rows_qs = [r for r in per_run if r["solver"] == "qss"]
    of_pairs = pair_condition(rows_cv, rows_qs)

    of_report = dict(
        campaign="E15_signature_map_OF",
        markers="tau_main=argmax(dT/dt); tau_first=first qualifying dT/dt peak",
        tend_mult=jobs.get("tend_mult", 2.0),
        wall_cap_s=jobs.get("wall_cap_s", 900),
        n_conditions=len(of_pairs),
        results=of_pairs,
    )
    (OUT / "e15_signature_map_of.json").write_text(json.dumps(of_report, indent=2))

    py_path = OUT / "e15_signature_map_python.json"
    py_pairs = []
    py_by_key = {}
    if py_path.is_file():
        py = json.loads(py_path.read_text())
        for r in py["results"]:
            if r.get("status") == "skipped_presize" or "py_cvode" not in r:
                continue
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
        of_dZ = r["of_qss"]["maxAbs_dZ"]
        py_dZ = py["py_qss"]["maxAbs_dZ"]
        of_tau = r["of_qss"]["tau_main_s"]
        py_tau = py["py_qss"]["tau_main_s"]
        diffs.append(
            dict(
                T0=r["T0"],
                p_atm=r["p_atm"],
                phi=r["phi"],
                delta_tau_main_ratio_OF_over_Py=safe_div(of_tau, py_tau),
                delta_Teq_ratio_OF_over_Py=safe_div(of_dT, py_dT),
                drift_ratio_OF_over_Py=safe_div(of_dZ, py_dZ),
                of_delta_Teq=of_dT,
                py_delta_Teq=py_dT,
                of_maxAbs_dZ=of_dZ,
                py_maxAbs_dZ=py_dZ,
                of_failure=r.get("failure"),
                py_failure=py.get("failure"),
            )
        )
    (OUT / "e15_of_vs_py_diffs.json").write_text(
        json.dumps(dict(n=len(diffs), results=diffs), indent=2)
    )

    plot_path = OUT / "e15_drift_vs_dTeq.png"
    plot_drift_vs_dteq(of_pairs, py_pairs, plot_path)

    picks = select_attribution(of_pairs, py_by_key)
    # JSON-safe (no bare NaN)
    def _clean(o):
        if isinstance(o, float) and not np.isfinite(o):
            return None
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_clean(v) for v in o]
        return o

    (OUT / "e15_2_attribution_points.json").write_text(
        json.dumps(dict(n=len(picks), points=_clean(picks)), indent=2)
    )

    of_md = [
        "# E15 OpenFOAM signature map",
        "",
        "Markers: **τ_main** = global max dT/dt; **τ_first** = first qualifying dT/dt peak.",
        f"endTime = {jobs.get('tend_mult', 2.0)}× Cantera-presized main τ; "
        f"wall cap = {jobs.get('wall_cap_s', 900)} s; batch width 8.",
        "",
        "| T0 | p | φ | τ_main,Q [ms] | τ_first,Q [ms] | Teq,Q | ΔTeq [K] | max\\|dZ\\| Q | wall Q [s] | failure |",
        "|---:|--:|--:|--------------:|---------------:|------:|---------:|-----------:|-----------:|---------|",
    ]
    for r in of_pairs:
        qs = r["of_qss"]
        tf = qs["tau_first_s"]
        tf_ms = tf * 1e3 if np.isfinite(tf) else float("nan")
        tm = qs["tau_main_s"] * 1e3 if np.isfinite(qs["tau_main_s"]) else float("nan")
        of_md.append(
            f"| {r['T0']:.0f} | {r['p_atm']:.0f} | {r['phi']:.1f} | "
            f"{tm:.3f} | {tf_ms:.3f} | "
            f"{qs['Teq'] if np.isfinite(qs['Teq']) else float('nan'):.1f} | "
            f"{r['delta_Teq'] if np.isfinite(r['delta_Teq']) else float('nan'):+.1f} | "
            f"{qs['maxAbs_dZ'] if np.isfinite(qs['maxAbs_dZ']) else float('nan'):.2e} | "
            f"{qs['wall_s'] if np.isfinite(qs['wall_s']) else float('nan'):.0f} | "
            f"{r.get('failure') or '—'} |"
        )
    (OUT / "E15_SIGNATURE_MAP_OF.md").write_text("\n".join(of_md) + "\n")

    diff_md = [
        "# E15 OF vs Python difference maps",
        "",
        "| T0 | p | φ | Δτ_main OF/Py | ΔTeq OF/Py | drift OF/Py | OF ΔTeq [K] | Py ΔTeq [K] |",
        "|---:|--:|--:|--------------:|-----------:|------------:|------------:|------------:|",
    ]
    for d in diffs:
        diff_md.append(
            f"| {d['T0']:.0f} | {d['p_atm']:.0f} | {d['phi']:.1f} | "
            f"{fmt(d['delta_tau_main_ratio_OF_over_Py'])} | "
            f"{fmt(d['delta_Teq_ratio_OF_over_Py'])} | "
            f"{fmt(d['drift_ratio_OF_over_Py'])} | "
            f"{fmt(d['of_delta_Teq'], 1)} | {fmt(d['py_delta_Teq'], 1)} |"
        )
    (OUT / "E15_OF_VS_PY_DIFFS.md").write_text("\n".join(diff_md) + "\n")

    n_ok = sum(1 for r in of_pairs if r["status"] == "ok")
    n_fail = len(of_pairs) - n_ok
    ok_pairs = [r for r in of_pairs if r["status"] == "ok"]
    med_dT_of = (
        float(np.nanmedian([r["delta_Teq"] for r in ok_pairs if np.isfinite(r["delta_Teq"])]))
        if ok_pairs
        else float("nan")
    )
    med_dT_py = (
        float(np.nanmedian([r["delta_Teq"] for r in py_pairs if np.isfinite(r["delta_Teq"])]))
        if py_pairs
        else float("nan")
    )
    # Robust amplitude ratio among ok pairs with same-sign nonzero ΔTeq
    amp_ratios = []
    for d in diffs:
        if d.get("of_failure") or d.get("py_failure"):
            continue
        a, b = d["of_delta_Teq"], d["py_delta_Teq"]
        if a is None or b is None:
            continue
        if not (np.isfinite(a) and np.isfinite(b)) or abs(b) < 1.0:
            continue
        amp_ratios.append(abs(a) / abs(b))
    med_amp = float(np.nanmedian(amp_ratios)) if amp_ratios else float("nan")
    signed = [
        d["delta_Teq_ratio_OF_over_Py"]
        for d in diffs
        if d["delta_Teq_ratio_OF_over_Py"] is not None
        and np.isfinite(d["delta_Teq_ratio_OF_over_Py"])
        and not d.get("of_failure")
    ]
    med_signed = float(np.nanmedian(signed)) if signed else float("nan")
    drift_rats = [
        d["drift_ratio_OF_over_Py"]
        for d in diffs
        if d["drift_ratio_OF_over_Py"] is not None
        and np.isfinite(d["drift_ratio_OF_over_Py"])
        and not d.get("of_failure")
    ]
    med_drift = float(np.nanmedian(drift_rats)) if drift_rats else float("nan")

    n_timeout = sum(
        1
        for r in per_run
        if r.get("failure") == "wall_timeout"
    )
    combined = [
        "# E15 Signature Map",
        "",
        "## Setup",
        "",
        "- Grid: pre-sized RUN set from `e15_presize.json` (τ_Cantera ≤ 50 ms).",
        "- **endTime** = 2× Cantera-presized main τ; **wall cap** = 900 s/run; OF batch **8-wide**.",
        "- Ignition markers (identical OF & Python): **τ_main** = argmax(dT/dt); "
        "**τ_first** = first qualifying dT/dt peak.",
        "- Failures recorded as data points (not skipped).",
        "",
        "## Summary",
        "",
        f"- OF conditions: **{len(of_pairs)}** (ok={n_ok}, fail/partial={n_fail}; "
        f"raw wall_timeout runs={n_timeout})",
        f"- Median ΔTeq (QSS−CVODE), ok only: OF **{med_dT_of:+.1f} K**, Py **{med_dT_py:+.1f} K**",
        f"- Median |ΔTeq|_OF / |ΔTeq|_Py (ok, |Py|≥1 K): **{med_amp:.2f}×** "
        f"(signed median OF/Py={med_signed:.2f}×)",
        f"- Median drift OF/Py (ok): **{med_drift:.2f}×**",
        "",
        "## Artifacts",
        "",
        "- OF map: `E15_SIGNATURE_MAP_OF.md` / `e15_signature_map_of.json`",
        "- Python map: `E15_SIGNATURE_MAP_PYTHON.md` / `e15_signature_map_python.json`",
        "- Difference maps: `E15_OF_VS_PY_DIFFS.md` / `e15_of_vs_py_diffs.json`",
        "- Drift vs ΔTeq: [`e15_drift_vs_dTeq.png`](e15_drift_vs_dTeq.png)",
        "",
        "## E15.2 attribution points (selected)",
        "",
        "| label | T0 | p [atm] | φ | OF ΔTeq [K] | OF max\\|dZ\\| QSS | τ_first,Q |",
        "|-------|---:|--------:|--:|------------:|------------------:|----------:|",
    ]
    for p in picks:
        tf = p.get("of_tau_first_qss")
        tf_s = f"{tf*1e3:.3f} ms" if tf is not None and np.isfinite(tf) else "—"
        combined.append(
            f"| {p['label']} | {p['T0']:.0f} | {p['p_atm']:.0f} | {p['phi']:.1f} | "
            f"{fmt(p['of_delta_Teq'], 1)} | {fmt(p['of_maxAbs_dZ_qss'])} | {tf_s} |"
        )
    combined += ["", "### Rationale", ""]
    for p in picks:
        combined.append(f"- **{p['label']}**: {p['rationale']}")
    combined += [
        "",
        "## E15.3",
        "",
        "**HUMAN GATE** — awaiting advisor input before toggle campaign.",
        "",
        "---",
        "",
        "## Appendix: OF map table",
        "",
    ]
    combined.extend(of_md[5:])
    combined += ["", "## Appendix: OF vs Py difference table", ""]
    combined.extend(diff_md[2:])
    (OUT / "E15_SIGNATURE_MAP.md").write_text("\n".join(combined) + "\n")

    (OUT / "STATUS.md").write_text(
        "\n".join(
            [
                "# E15 status — reshaped after E14.5",
                "",
                "| Step                             | Status                                         |",
                "| ----------------------------------| ------------------------------------------------|",
                "| E14.5 element drift              | **DONE** — Component B = CHEMEQ2 element drift |",
                "| E15.1 config diff                | **DONE** — `E15_1_CONFIG_DIFF.md`              |",
                "| E15 Cantera pre-size             | **DONE** — 38/60 RUN (`e15_presize.json`)      |",
                "| E15 Python signature map         | **DONE** — robust markers (`E15_SIGNATURE_MAP_PYTHON.md`) |",
                "| E15 OF signature map             | **DONE** — `E15_SIGNATURE_MAP.md`              |",
                "| E15.2 toggle attribution @ 3 pts | **SELECTED** — `e15_2_attribution_points.json` |",
                "| E15.3 HUMAN GATE                 | **PENDING** — advisor input                    |",
                "",
                "E14.5: `../e14_ledger/E14_5_ELEMENT_DRIFT.md`",
                "",
            ]
        )
    )
    print(f"Wrote {OUT/'E15_SIGNATURE_MAP.md'}; picks={len(picks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

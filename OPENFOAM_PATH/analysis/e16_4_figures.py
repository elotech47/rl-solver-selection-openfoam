#!/usr/bin/env python3
"""E16.4 publication figures — one composite per paper condition (panels a–d)."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONDS = ROOT / "validation/e16_parity/E16_4_CONDITIONS.json"
RUNS = ROOT / "validation/e16_parity/e16_4_runs"
FIGDIR = ROOT / "analysis" / "e16_4_figures"
FIGDIR.mkdir(parents=True, exist_ok=True)

OF_MODES = ("cvodeOnly", "qssOnly", "rlAdaptive")
PY_MODES = ("CVODE", "QSS", "AdaptiveRL")
COLORS = {
    "cvodeOnly": "#1f77b4",
    "qssOnly": "#ff7f0e",
    "rlAdaptive": "#2ca02c",
    "CVODE": "#1f77b4",
    "QSS": "#ff7f0e",
    "AdaptiveRL": "#2ca02c",
}


def ignition_delay(temps: np.ndarray, times: np.ndarray) -> float | None:
    if temps is None or len(temps) < 2:
        return None
    if (float(temps[-1]) - float(temps[0])) <= 10 and float(temps[0]) <= 1000:
        return 0.0
    dT = np.diff(temps) / np.diff(times)
    return float(times[int(np.argmax(dT))])


def read_chemfoam_out(path: Path):
    if not path.is_file():
        return np.array([]), np.array([])
    t, T = [], []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            try:
                t.append(float(parts[0]))
                T.append(float(parts[1]))
            except ValueError:
                continue
    return np.asarray(t), np.asarray(T)


def read_foam_scalar(path: Path) -> float | None:
    if not path.is_file():
        return None
    text = path.read_text()
    m = re.search(r"internalField\s+uniform\s+([^\s;]+)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"^\s*\d+\s*\n\s*\(\s*\n\s*([^\s]+)", text, re.M)
    if m:
        return float(m.group(1))
    return None


def load_of(cid: str, mode: str):
    d = RUNS / f"{cid}_{mode}"
    t, T = read_chemfoam_out(d / "chemFoam.out")
    wall = None
    meta = d / "run_meta.json"
    if meta.is_file():
        wall = json.loads(meta.read_text()).get("wall_sec")
    chem = read_foam_scalar(d / "fields" / "chemCpuTime")
    decisions = []
    dec = d / "rl_decisions.csv"
    if dec.is_file():
        with dec.open() as f:
            r = csv.DictReader(f)
            for row in r:
                decisions.append(
                    {
                        "time": float(row.get("time", 0)),
                        "flag": int(float(row.get("flag", 1))),
                        "p": float(row.get("p", 0.5)),
                        "T": float(row.get("T", row.get("temp", "nan"))),
                    }
                )
    return {
        "t": t,
        "T": T,
        "wall": wall,
        "chem_cpu": chem,
        "decisions": decisions,
        "tau": ignition_delay(T, t) if len(T) else None,
        "T_final": float(T[-1]) if len(T) else None,
    }


def load_py(cid: str, mode: str):
    d = RUNS / f"{cid}_python"
    npz = d / f"{mode}_traj.npz"
    if not npz.is_file():
        return None
    z = np.load(npz)
    t = np.asarray(z["times"])
    T = np.asarray(z["T"])
    decisions = []
    if mode == "AdaptiveRL":
        dec = d / "decisions.csv"
        if dec.is_file():
            with dec.open() as f:
                r = csv.DictReader(f)
                for row in r:
                    decisions.append(
                        {
                            "time": float(row["time"]),
                            "flag": int(row["executed_action"]),
                            "p": float(row["p"]),
                            "T": float(row["T"]),
                        }
                    )
    return {
        "t": t,
        "T": T,
        "wall": float(z["wall_time"]) if "wall_time" in z.files else None,
        "chem_cpu": float(z["cpu_time"]) if "cpu_time" in z.files else None,
        "decisions": decisions,
        "tau": ignition_delay(T, t) if len(T) else None,
        "T_final": float(T[-1]) if len(T) else None,
    }


def ood_frac(decs) -> float:
    if not decs:
        return float("nan")
    p = np.asarray([d["p"] for d in decs], dtype=float)
    return float(np.mean(np.abs(p - 0.5) < 0.1))


def cvode_frac(decs) -> float:
    if not decs:
        return float("nan")
    return float(np.mean([d["flag"] == 0 for d in decs]))


def plot_condition(c: dict) -> dict:
    cid = c["id"]
    of = {m: load_of(cid, m) for m in OF_MODES}
    py = {m: load_py(cid, m) for m in PY_MODES}

    fig = plt.figure(figsize=(13.0, 12.0), constrained_layout=True)
    gs = fig.add_gridspec(3, 2, height_ratios=[1.1, 1.0, 1.0])
    ax_T = fig.add_subplot(gs[0, 0])
    ax_dec_t = fig.add_subplot(gs[0, 1])
    ax_dec_T = fig.add_subplot(gs[1, :])
    ax_tau = fig.add_subplot(gs[2, 0])
    ax_cpu = fig.add_subplot(gs[2, 1])

    header = (
        f"E16.4 {cid} {c['label']} — T0={c['T0']} K, p={c['p_atm']} atm, Z={c['Z']}\n"
        f"dt={c['dt']:g} s, window=maxChemDeltaT={c['dt']:g} s, "
        f"num_steps={c['num_steps']}, decision_interval={c['dt']*c['num_steps']:g} s\n"
        f"source: handoff/configs/example_ndodecane.yaml"
    )
    fig.suptitle(header, fontsize=10)

    # (a) T(t)
    for m in OF_MODES:
        if len(of[m]["t"]):
            ax_T.plot(
                of[m]["t"] * 1e3,
                of[m]["T"],
                color=COLORS[m],
                ls="-",
                lw=1.8,
                label=f"OF-{m}",
            )
    for m in PY_MODES:
        if py[m] is not None and len(py[m]["t"]):
            ax_T.plot(
                py[m]["t"] * 1e3,
                py[m]["T"],
                color=COLORS[m],
                ls="--",
                lw=1.6,
                label=f"Py-{m}",
            )
    ax_T.set_xlabel("t [ms]")
    ax_T.set_ylabel("T [K]")
    ax_T.set_title("(a) Temperature profiles")
    ax_T.legend(fontsize=7, ncol=2)
    ax_T.grid(True, alpha=0.3)

    # (b) decision timeline vs time AND vs T (progress-space); OF + Py stacked
    ax_dec_t.set_title("(b1) Decisions vs time (p=P(QSS))")
    ax_dec_T.set_title("(b2) Decisions vs T / progress-space (p=P(QSS))")
    for label, data, yoff, marker in (
        ("OF", of["rlAdaptive"], 0.0, "o"),
        ("Py", py["AdaptiveRL"] if py["AdaptiveRL"] else {"decisions": []}, 1.2, "s"),
    ):
        decs = data.get("decisions", [])
        if not decs:
            continue
        tt = np.asarray([d["time"] for d in decs]) * 1e3
        TT = np.asarray([d["T"] for d in decs])
        pp = np.asarray([d["p"] for d in decs])
        fl = np.asarray([d["flag"] for d in decs])
        yflag = fl + yoff
        ax_dec_t.scatter(
            tt,
            yflag,
            c=pp,
            cmap="coolwarm",
            vmin=0,
            vmax=1,
            s=16,
            marker=marker,
            label=f"{label} (0=CVODE,1=QSS; +{yoff:g})",
            alpha=0.85,
        )
        ax_dec_T.scatter(
            TT,
            yflag,
            c=pp,
            cmap="coolwarm",
            vmin=0,
            vmax=1,
            s=16,
            marker=marker,
            edgecolors=["k" if f == 0 else "none" for f in fl],
            linewidths=0.35,
            label=f"{label}",
            alpha=0.85,
        )
    ax_dec_t.set_xlabel("t [ms]")
    ax_dec_t.set_ylabel("flag (+stack)")
    ax_dec_t.set_yticks([0, 1, 1.2, 2.2])
    ax_dec_t.set_yticklabels(["OF-CVODE", "OF-QSS", "Py-CVODE", "Py-QSS"])
    ax_dec_t.legend(fontsize=7)
    ax_dec_t.grid(True, alpha=0.3)
    ax_dec_T.set_xlabel("T [K]")
    ax_dec_T.set_ylabel("flag (+stack)")
    ax_dec_T.set_yticks([0, 1, 1.2, 2.2])
    ax_dec_T.set_yticklabels(["OF-CVODE", "OF-QSS", "Py-CVODE", "Py-QSS"])
    ax_dec_T.legend(fontsize=7)
    ax_dec_T.grid(True, alpha=0.3)
    sm = plt.cm.ScalarMappable(cmap="coolwarm", norm=plt.Normalize(0, 1))
    sm.set_array([])
    fig.colorbar(sm, ax=[ax_dec_t, ax_dec_T], fraction=0.02, pad=0.02, label="p = P(QSS)")

    # (c) ignition delay bars
    labels = []
    taus = []
    bar_colors = []
    for m in OF_MODES:
        labels.append(f"OF-{m}")
        taus.append(of[m]["tau"] if of[m]["tau"] is not None else np.nan)
        bar_colors.append(COLORS[m])
    for m in PY_MODES:
        labels.append(f"Py-{m}")
        tau = py[m]["tau"] if py[m] and py[m]["tau"] is not None else np.nan
        taus.append(tau)
        bar_colors.append(COLORS[m])
    x = np.arange(len(labels))
    ax_tau.bar(x, [t * 1e3 if t == t else 0 for t in taus], color=bar_colors, alpha=0.85)
    ax_tau.set_xticks(x)
    ax_tau.set_xticklabels(labels, rotation=35, ha="right", fontsize=7)
    ax_tau.set_ylabel(r"$\tau_{\mathrm{ign}}$ [ms]")
    ax_tau.set_title("(c) Ignition delay")
    ax_tau.grid(True, axis="y", alpha=0.3)

    # annotate % deviations
    def pct(a, b):
        if a is None or b is None or b == 0 or a != a or b != b:
            return None
        return 100.0 * (a - b) / abs(b)

    notes = []
    for ofm, pym in (
        ("cvodeOnly", "CVODE"),
        ("qssOnly", "QSS"),
        ("rlAdaptive", "AdaptiveRL"),
    ):
        d = pct(of[ofm]["tau"], py[pym]["tau"] if py[pym] else None)
        if d is not None:
            notes.append(f"OF-{ofm} vs Py: {d:+.2f}%")
    d_of = pct(of["rlAdaptive"]["tau"], of["cvodeOnly"]["tau"])
    d_py = pct(
        py["AdaptiveRL"]["tau"] if py["AdaptiveRL"] else None,
        py["CVODE"]["tau"] if py["CVODE"] else None,
    )
    if d_of is not None:
        notes.append(f"OF-rl vs OF-cvode: {d_of:+.2f}%")
    if d_py is not None:
        notes.append(f"Py-rl vs Py-cvode: {d_py:+.2f}%")
    ax_tau.text(
        0.02,
        0.98,
        "\n".join(notes),
        transform=ax_tau.transAxes,
        va="top",
        fontsize=7,
        family="monospace",
    )

    # (d) Chemistry-only primary; wall secondary
    wall_of = [of[m]["wall"] or np.nan for m in OF_MODES]
    chem_of = [of[m]["chem_cpu"] if of[m]["chem_cpu"] is not None else np.nan for m in OF_MODES]
    wall_py = [py[m]["wall"] if py[m] and py[m]["wall"] is not None else np.nan for m in PY_MODES]
    chem_py = [
        py[m]["chem_cpu"] if py[m] and py[m]["chem_cpu"] is not None else np.nan
        for m in PY_MODES
    ]
    width = 0.35
    xo = np.arange(3)
    ax_cpu.bar(xo - width / 2, chem_of, width, label="OF chemCpu (primary)", color="#333333", alpha=0.85)
    ax_cpu.bar(xo + width / 2, wall_of, width, label="OF wall (secondary)", color="#aaaaaa", alpha=0.55)
    ax_cpu.bar(xo + 3 - width / 2, chem_py, width, label="Py cpu (primary)", color="#d95f02", alpha=0.85)
    ax_cpu.bar(xo + 3 + width / 2, wall_py, width, label="Py wall (secondary)", color="#a6d854", alpha=0.55)
    ax_cpu.set_xticks(list(xo) + list(xo + 3))
    ax_cpu.set_xticklabels(
        [f"OF-{m}" for m in OF_MODES] + [f"Py-{m}" for m in PY_MODES],
        rotation=35,
        ha="right",
        fontsize=7,
    )
    ax_cpu.set_ylabel("time [s]")
    ax_cpu.set_title("(d) Chemistry-only CPU (primary) / wall (secondary)")
    ax_cpu.legend(fontsize=6)
    ax_cpu.grid(True, axis="y", alpha=0.3)

    # chemistry-only speedups + CVODE usage
    def sp(ref, x):
        if ref is None or x is None or x != x or ref != ref or x <= 0:
            return None
        return ref / x

    cv_chem = of["cvodeOnly"]["chem_cpu"]
    cv_wall = of["cvodeOnly"]["wall"]
    annot = []
    for m in ("rlAdaptive", "qssOnly"):
        s = sp(cv_chem, of[m]["chem_cpu"])
        if s is not None:
            annot.append(f"OF {m} chem speedup: {s:.2f}x")
        sw = sp(cv_wall, of[m]["wall"])
        if sw is not None:
            annot.append(f"OF {m} wall speedup: {sw:.2f}x")
    cf_of = cvode_frac(of["rlAdaptive"]["decisions"])
    cf_py = cvode_frac(py["AdaptiveRL"]["decisions"] if py["AdaptiveRL"] else [])
    if cf_of == cf_of:
        annot.append(f"OF CVODE-usage frac: {cf_of:.3f}")
    if cf_py == cf_py:
        annot.append(f"Py CVODE-usage frac: {cf_py:.3f}")
    ood_of = ood_frac(of["rlAdaptive"]["decisions"])
    ood_py = ood_frac(py["AdaptiveRL"]["decisions"] if py["AdaptiveRL"] else [])
    if ood_of == ood_of:
        annot.append(f"OF OOD |p-0.5|<0.1: {ood_of:.3f}")
    if ood_py == ood_py:
        annot.append(f"Py OOD |p-0.5|<0.1: {ood_py:.3f}")
    ax_cpu.text(
        0.02,
        0.98,
        "\n".join(annot),
        transform=ax_cpu.transAxes,
        va="top",
        fontsize=6.5,
        family="monospace",
    )

    out = FIGDIR / f"E16_4_{cid}_{c['label']}.png"
    fig.savefig(out, dpi=300)
    fig.savefig(out.with_suffix(".pdf"))
    plt.close(fig)

    metrics = {
        "id": cid,
        "label": c["label"],
        "figure": str(out),
        "of": {
            m: {
                "tau": of[m]["tau"],
                "T_final": of[m]["T_final"],
                "wall": of[m]["wall"],
                "chem_cpu": of[m]["chem_cpu"],
                "cvode_frac": cvode_frac(of[m]["decisions"]) if m == "rlAdaptive" else None,
                "ood_frac": ood_frac(of[m]["decisions"]) if m == "rlAdaptive" else None,
            }
            for m in OF_MODES
        },
        "py": {
            m: {
                "tau": py[m]["tau"] if py[m] else None,
                "T_final": py[m]["T_final"] if py[m] else None,
                "wall": py[m]["wall"] if py[m] else None,
                "chem_cpu": py[m]["chem_cpu"] if py[m] else None,
                "cvode_frac": cvode_frac(py[m]["decisions"])
                if py[m] and m == "AdaptiveRL"
                else None,
                "ood_frac": ood_frac(py[m]["decisions"])
                if py[m] and m == "AdaptiveRL"
                else None,
            }
            for m in PY_MODES
        },
    }
    return metrics


def main() -> None:
    cfg = json.loads(CONDS.read_text())
    all_m = []
    for c in cfg["conditions"]:
        print(f"[figures] {c['id']} ...", flush=True)
        all_m.append(plot_condition(c))
    (FIGDIR / "metrics.json").write_text(json.dumps(all_m, indent=2))
    print(f"Wrote figures under {FIGDIR}")


if __name__ == "__main__":
    main()

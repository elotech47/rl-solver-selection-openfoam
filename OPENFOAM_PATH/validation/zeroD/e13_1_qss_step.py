#!/usr/bin/env python3
"""E13.1 — Python-QSS single 1 µs step from pinned MidT states (refit thermo).

Runs handoff QSS (parity target for OF-QSS) at each pinned (T,Y,p) state.
Writes ΔY, ΔT, OF-ready initialConditions (mass-fraction basis), and compares
to OF chemFoamDebug QSS dumps when present under e13_qss/of_runs/.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import cantera as ct
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
OUT = ROOT / "validation/zeroD/e13_qss"
DT = 1e-6
TEMPS = (1300.0, 1500.0, 1700.0, 2000.0)

QSS_CONFIG = dict(
    epsmin=0.02,
    epsmax=100.0,
    dtmin=1e-12,
    dtmax=1e-6,
    itermax=2,
    abstol=1e-11,
)


def midt_moles(gas: ct.Solution) -> dict[str, float]:
    names = {n.lower(): n for n in gas.species_names}
    return {
        names["o2"]: 0.20775813522367179,
        names["n2"]: 0.7811705884410058,
        names["nc12h26"]: 0.01107127633532227,
    }


def pin_states() -> list[dict]:
    gas = ct.Solution(str(YAML))
    gas.TPX = 800.0, 10 * ct.one_atm, midt_moles(gas)
    r = ct.IdealGasConstPressureReactor(gas)
    sim = ct.ReactorNet([r])
    targets = list(TEMPS)
    pinned = []
    while sim.time < 0.01 and targets:
        sim.step()
        if r.T >= targets[0]:
            pinned.append(
                dict(
                    T=float(r.T),
                    P=float(r.thermo.P),
                    t=float(sim.time),
                    Y=r.thermo.Y.copy(),
                    names=list(gas.species_names),
                )
            )
            targets.pop(0)
    return pinned


def load_pinned() -> list[dict]:
    npz_path = OUT / "pinned_states.npz"
    if npz_path.is_file():
        z = np.load(npz_path, allow_pickle=True)
        if "Y" in z and "names" in z:
            names = list(z["names"])
            Y_all = z["Y"]
            Ts = z["Ts"]
            Ps = z["Ps"]
            ts = z["ts"] if "ts" in z else np.zeros(len(Ts))
            return [
                dict(T=float(Ts[i]), P=float(Ps[i]), t=float(ts[i]), Y=Y_all[i], names=names)
                for i in range(len(Ts))
            ]
    return pin_states()


def stub_sundials():
    if "SundialsPy" not in sys.modules:
        _sp = types.ModuleType("SundialsPy")
        _sp.cvode = types.ModuleType("SundialsPy.cvode")
        sys.modules["SundialsPy"] = _sp
        sys.modules["SundialsPy.cvode"] = _sp.cvode


def qss_one_step(gas: ct.Solution, T: float, P: float, Y: np.ndarray, dt: float) -> tuple[float, np.ndarray]:
    from solver_selection_handoff.utils import create_qss_solver

    gas.TPY = T, P, Y
    integ = create_qss_solver(gas, P, QSS_CONFIG)
    y0 = np.concatenate([[gas.T], gas.Y])
    integ.setState(y0.tolist(), 0.0)
    integ.integrateToTime(dt)
    yout = np.asarray(integ.y, dtype=float)
    T1 = max(yout[0], 200.0)
    Y1 = np.maximum(yout[1:], 0.0)
    s = Y1.sum()
    if s > 0:
        Y1 /= s
    return T1, Y1


def write_of_ic(state: dict, tag: str) -> Path:
    ic_dir = OUT / "of_ic" / tag
    ic_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "/* E13.1 pinned state — auto-generated for chemFoam_0D */",
        "FoamFile",
        "{",
        "    version     2.0;",
        "    format      ascii;",
        "    class       dictionary;",
        "    object      initialConditions;",
        "}",
        "",
        "constantProperty pressure;",
        "fractionBasis   mass;",
        "",
        "fractions",
        "{",
    ]
    for name, yi in zip(state["names"], state["Y"]):
        lines.append(f"    {name:<16} {yi:.17g};")
    lines.extend(
        [
            "}",
            "",
            f"p               {state['P']:.10g};",
            f"T               {state['T']:.10g};",
            "",
        ]
    )
    (ic_dir / "initialConditions").write_text("\n".join(lines))
    meta = {k: v for k, v in state.items() if k != "Y"}
    meta["tag"] = tag
    (ic_dir / "state_meta.json").write_text(json.dumps(meta, indent=2))
    return ic_dir


def write_e8_style(state: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# species Y  t={state['t']:.8g} Tprev={state['T']:.6g}"]
    for name, yi in zip(state["names"], state["Y"]):
        lines.append(f"{name} {yi:.17g}")
    path.write_text("\n".join(lines) + "\n")


def parse_chemfoam_out(path: Path) -> tuple[np.ndarray, np.ndarray]:
    t, T = [], []
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            t.append(float(parts[0]))
            T.append(float(parts[1]))
    return np.asarray(t), np.asarray(T)


def compare_of(py_results: list[dict]) -> dict | None:
    of_root = OUT / "of_runs"
    if not of_root.is_dir():
        return None
    rows = []
    for pr in py_results:
        tag = pr["tag"]
        run_dir = of_root / tag
        out = run_dir / "chemFoam.out"
        if not out.is_file():
            continue
        t_of, T_of = parse_chemfoam_out(out)
        if len(T_of) < 2:
            continue
        dT_of = float(T_of[-1] - T_of[0])
        dT_py = pr["dT"]
        rel = abs(dT_of - dT_py) / max(abs(dT_py), 1e-30)
        rows.append(
            dict(
                tag=tag,
                T0=pr["T0"],
                dT_py=dT_py,
                dT_of=dT_of,
                rel_dT_pct=100 * rel,
                T_of_end=float(T_of[-1]),
                T_py_end=pr["T1"],
            )
        )
    if not rows:
        return None
    max_rel = max(r["rel_dT_pct"] for r in rows)
    return dict(n_compared=len(rows), rows=rows, max_rel_dT_pct=max_rel, gate_1pct=max_rel <= 1.0)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pinned = load_pinned()
    names = pinned[0]["names"]

    # Persist full npz if missing structured arrays
    np.savez_compressed(
        OUT / "pinned_states.npz",
        Y=np.array([s["Y"] for s in pinned]),
        Ts=np.array([s["T"] for s in pinned]),
        Ps=np.array([s["P"] for s in pinned]),
        ts=np.array([s["t"] for s in pinned]),
        names=np.array(names, dtype=object),
    )

    gas = ct.Solution(str(YAML))
    py_results = []
    for i, st in enumerate(pinned):
        tag = f"T{int(round(st['T']))}"
        T0, P, Y0 = st["T"], st["P"], np.asarray(st["Y"])
        T1, Y1 = qss_one_step(gas, T0, P, Y0, DT)
        dT = T1 - T0
        dY = Y1 - Y0
        pr = dict(
            tag=tag,
            T0=T0,
            P=P,
            t_pin=st["t"],
            dT=dT,
            T1=T1,
            max_abs_dY=float(np.max(np.abs(dY))),
            sum_dY=float(dY.sum()),
            l2_dY=float(np.linalg.norm(dY)),
        )
        py_results.append(pr)
        np.savez_compressed(
            OUT / f"py_qss_step_{tag}.npz",
            Y0=Y0,
            Y1=Y1,
            dY=dY,
            dT=np.array(dT),
            T0=np.array(T0),
            T1=np.array(T1),
            names=np.array(names, dtype=object),
        )
        write_of_ic(st, tag)
        write_e8_style(st, OUT / "of_ic" / tag / "e8_crash_state.dat")
        print(
            f"  {tag}: T0={T0:.2f} → T1={T1:.2f}  ΔT={dT:+.4f} K  "
            f"max|ΔY|={pr['max_abs_dY']:.3e}"
        )

    of_cmp = compare_of(py_results)
    summary = dict(
        campaign="E13.1",
        mechanism=str(YAML.relative_to(ROOT)),
        dt_s=DT,
        qss_config=QSS_CONFIG,
        n_states=len(py_results),
        python=py_results,
        of_comparison=of_cmp,
        of_procedure="See e13_qss/OF_PROCEDURE.md and run_e13_1_of.sh",
    )
    (OUT / "e13_1_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {OUT / 'e13_1_summary.json'}")
    if of_cmp:
        print(f"OF comparison: {of_cmp['n_compared']} states, max|ΔΔT|/|ΔT|={of_cmp['max_rel_dT_pct']:.4f}%")
    else:
        print("OF comparison: pending (no of_runs/*/chemFoam.out yet)")
    return 0


if __name__ == "__main__":
    stub_sundials()
    raise SystemExit(main())

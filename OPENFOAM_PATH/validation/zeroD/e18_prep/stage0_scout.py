#!/usr/bin/env python3
"""E18 Stage 0 — ignition-viability scout (Cantera, BEFORE any 2D mesh).

Fuel: pure n-dodecane @ 300 K  |  Oxidizer: air @ T_air  |  p ∈ {1, 10} atm
Grid: a ∈ {50,100,200,400,800} s⁻¹ × T_air ∈ {1000,1050,1100,1200} K

Method (hours-scale, no Ember required):
  1) Mixing-line most-reactive mixture (MRM): Z∈[0.02,0.12], const-p 0D τ_ign.
  2) Strain residence τ_res = 1/a (opposed-jet order of magnitude).
  3) Viability: ignites if τ_ign finite and τ_ign / τ_res ≤ Da_max (default 0.5
     = "comfortably below residence"). Also report Da=1 boundary.
  4) Optional: Cantera CounterflowDiffusionFlame steady solve at shortlisted
     points (expensive on Luo) — records whether a hot flame exists.

Outputs under validation/zeroD/e18_prep/stage0_scout/
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]  # OPENFOAM_PATH
YAML = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
OUT = ROOT / "validation/zeroD/e18_prep/stage0_scout"

T_FUEL = 300.0
A_LIST = [50.0, 100.0, 200.0, 400.0, 800.0]
T_AIR_LIST = [1000.0, 1050.0, 1100.0, 1200.0]
P_ATM_LIST = [1.0, 10.0]
Z_LIST = np.linspace(0.01, 0.12, 12)
DA_COMFORT = 0.5  # τ_ign / τ_res ≤ this → "comfortable"
DA_MARGINAL = 1.0


def _fuel_name(gas) -> str:
    for n in ("n-C12H26", "nc12h26", "NC12H26"):
        if n in gas.species_names:
            return n
    raise SystemExit(f"n-dodecane not in mechanism: {gas.species_names[:5]}…")


def mix_state(gas, Z: float, T_air: float, P: float):
    """Enthalpy-weighted mix: fuel mass fraction Z, fuel@300K, air@T_air."""
    fname = _fuel_name(gas)
    gas.TPX = T_FUEL, P, {fname: 1.0}
    Yf, hf = gas.Y.copy(), gas.enthalpy_mass
    gas.TPX = T_air, P, {"O2": 0.21, "N2": 0.79}
    Ya, ha = gas.Y.copy(), gas.enthalpy_mass
    Y = Z * Yf + (1.0 - Z) * Ya
    h = Z * hf + (1.0 - Z) * ha
    gas.HPY = h, P, Y
    return float(gas.T), gas.X.copy(), gas.Y.copy()


def ign_delay(gas, T: float, P: float, X, t_end: float = 0.2) -> tuple[float, float]:
    """Return (τ_hot_ign, T_peak).

    Hot ignition = first time T exceeds max(T0+800, 1800) K — avoids counting
    n-dodecane NTC / cool-flame bumps as autoignition.
    """
    import cantera as ct

    gas.TPX = T, P, X
    r = ct.IdealGasConstPressureReactor(gas, clone=True)
    net = ct.ReactorNet([r])
    T0 = T
    T_thresh = max(T0 + 800.0, 1800.0)
    t = 0.0
    dt = 1e-7
    T_peak = T0
    tau = float("nan")
    while t < t_end:
        t_next = min(t + dt, t_end)
        net.advance(t_next)
        t = t_next
        T_peak = max(T_peak, float(r.T))
        if not (tau == tau) and r.T >= T_thresh:  # nan check
            tau = float(t)
            # continue a bit to record peak
            if t > tau + 2e-3:
                break
        if r.T > T0 + 50.0:
            dt = min(dt * 1.5, 5e-5)
        else:
            dt = min(dt * 1.2, 2e-4)
    return tau, float(T_peak)


def mrm_for_point(T_air: float, P_atm: float, a: float) -> dict:
    import cantera as ct

    P = P_atm * 101325.0
    gas = ct.Solution(str(YAML))
    best = None
    scan = []
    for Z in Z_LIST:
        Tmix, X, _Y = mix_state(gas, float(Z), T_air, P)
        # Skip absurdly cold mixes
        if Tmix < 600.0:
            tau, Tp = float("nan"), Tmix
        else:
            tau, Tp = ign_delay(gas, Tmix, P, X)
        row = dict(Z=float(Z), Tmix=float(Tmix), tau_s=tau, T_peak=Tp)
        scan.append(row)
        if np.isfinite(tau) and (best is None or tau < best["tau_s"]):
            best = row

    tau_res = 1.0 / a
    if best is None or not np.isfinite(best["tau_s"]):
        return dict(
            T_air=T_air,
            P_atm=P_atm,
            a=a,
            tau_res_s=tau_res,
            ignites=False,
            comfortable=False,
            marginal=False,
            Z_star=None,
            Tmix_star=None,
            tau_ign_s=None,
            T_peak_0D=None,
            Da_inv=None,  # τ_ign/τ_res
            scan=scan,
        )

    Da_inv = best["tau_s"] / tau_res
    return dict(
        T_air=T_air,
        P_atm=P_atm,
        a=a,
        tau_res_s=tau_res,
        ignites=True,
        comfortable=Da_inv <= DA_COMFORT,
        marginal=Da_inv <= DA_MARGINAL,
        Z_star=best["Z"],
        Tmix_star=best["Tmix"],
        tau_ign_s=best["tau_s"],
        T_peak_0D=best["T_peak"],
        Da_inv=Da_inv,
        # Stagnation-plane relative: fuel left (x=0), air right — MRM Z~0.05–0.08
        # sits on the air side of stoichiometric for heavy fuel (Z_st≈0.06).
        ignition_side="oxidizer-lean-of-stoich" if best["Z"] < 0.062 else "near-stoich/fuel-rich",
        scan=scan,
    )


def try_counterflow_steady(T_air: float, P_atm: float, a: float, width: float = 0.02) -> dict:
    """Optional steady diffusion-flame existence check (expensive)."""
    import cantera as ct

    P = P_atm * 101325.0
    gas = ct.Solution(str(YAML))
    fname = _fuel_name(gas)
    f = ct.CounterflowDiffusionFlame(gas, width=width)
    # Approximate: a ≈ (U_f + U_o)/width with equal momenta → set mdot from a
    # ρU ≈ a * width * ρ / 2 each side
    gas.TPX = T_FUEL, P, {fname: 1.0}
    rho_f = gas.density
    gas.TPX = T_air, P, {"O2": 0.21, "N2": 0.79}
    rho_o = gas.density
    U = 0.5 * a * width
    f.P = P
    f.fuel_inlet.mdot = rho_f * U
    f.fuel_inlet.T = T_FUEL
    f.fuel_inlet.X = {fname: 1.0}
    f.oxidizer_inlet.mdot = rho_o * U
    f.oxidizer_inlet.T = T_air
    f.oxidizer_inlet.X = {"O2": 0.21, "N2": 0.79}
    f.set_refine_criteria(ratio=4, slope=0.2, curve=0.3, prune=0.05)
    try:
        f.solve(loglevel=0, auto=True)
        Tmax = float(np.max(f.T))
        # axial location of T peak relative to midplane
        x = f.grid
        i = int(np.argmax(f.T))
        x_mid = 0.5 * width
        return dict(
            ok=True,
            Tmax=Tmax,
            lit=Tmax > T_air + 200.0,
            x_Tpeak=float(x[i]),
            x_mid=x_mid,
            side="fuel" if x[i] < x_mid else "oxidizer",
            strain_max=float(f.strain_rate("max")),
        )
    except Exception as e:
        return dict(ok=False, error=str(e)[:200], lit=False)


def _worker(args):
    T_air, P_atm, a = args
    t0 = time.time()
    row = mrm_for_point(T_air, P_atm, a)
    row["wall_s"] = time.time() - t0
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--counterflow-check", action="store_true",
                    help="Run steady CF checks on comfortable shortlist (slow)")
    ap.add_argument("--p-atm", type=float, nargs="*", default=None,
                    help="Override pressures (default 1 and 10)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    pressures = args.p_atm or P_ATM_LIST
    jobs = [(T, P, a) for P in pressures for T in T_AIR_LIST for a in A_LIST]
    print(f"E18 Stage0 scout: {len(jobs)} points, jobs={args.jobs}")
    print(f"YAML={YAML}")

    results = []
    # ProcessPool: each worker loads Cantera fresh
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(_worker, j): j for j in jobs}
        for k, fut in enumerate(as_completed(futs), 1):
            row = fut.result()
            results.append(row)
            tag = "COMFORT" if row.get("comfortable") else (
                "MARGINAL" if row.get("marginal") else (
                    "IGN_SLOW" if row.get("ignites") else "NO_IGN"))
            tau = row.get("tau_ign_s")
            tau_ms = f"{tau*1e3:.2f}" if tau else "nan"
            print(
                f"[{k}/{len(jobs)}] p={row['P_atm']:g}atm T_air={row['T_air']:.0f} "
                f"a={row['a']:.0f} → {tag} τ={tau_ms}ms "
                f"Da⁻¹={row.get('Da_inv')} Z*={row.get('Z_star')} ({row['wall_s']:.1f}s)"
            )

    results.sort(key=lambda r: (r["P_atm"], r["T_air"], r["a"]))

    # CSV summary (no nested scan)
    csv_path = OUT / "scout_grid.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "P_atm", "T_air", "a", "tau_res_s", "ignites", "comfortable",
                "marginal", "Z_star", "Tmix_star", "tau_ign_s", "T_peak_0D",
                "Da_inv", "ignition_side", "wall_s",
            ],
        )
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k) for k in w.fieldnames})

    (OUT / "scout_grid_full.json").write_text(json.dumps(results, indent=2))

    # Pick production recommendation
    comfort = [r for r in results if r.get("comfortable")]
    # Prefer p=10 if any comfort (thesis/OF case history); else p=1
    # Prefer a in [100,300], T_air as low as physics allows
    def score(r):
        a_pen = 0 if 100 <= r["a"] <= 300 else abs(r["a"] - 200) / 200
        # prefer lower T_air (harder / more interesting) among comfortable
        return (0 if r["P_atm"] == 10 else 1, a_pen, r["T_air"], r["Da_inv"])

    pick = None
    if comfort:
        pick = min(comfort, key=score)
    else:
        marg = [r for r in results if r.get("marginal")]
        if marg:
            pick = min(marg, key=score)
        else:
            ign = [r for r in results if r.get("ignites")]
            if ign:
                pick = min(ign, key=lambda r: (r["Da_inv"], r["T_air"], r["a"]))

    # Boundary table per pressure
    boundary = {}
    for P in pressures:
        sub = [r for r in results if r["P_atm"] == P]
        # for each a, min T_air that is comfortable / marginal / ignites
        by_a = {}
        for a in A_LIST:
            pts = [r for r in sub if r["a"] == a]
            by_a[a] = {
                "min_T_comfortable": min((r["T_air"] for r in pts if r["comfortable"]), default=None),
                "min_T_marginal": min((r["T_air"] for r in pts if r["marginal"]), default=None),
                "min_T_ignites": min((r["T_air"] for r in pts if r["ignites"]), default=None),
            }
        boundary[str(P)] = by_a

    cf_results = []
    if args.counterflow_check and pick:
        print("Steady counterflow check on pick + neighbors…")
        shortlist = [pick]
        for r in results:
            if r["P_atm"] == pick["P_atm"] and r["comfortable"] and r not in shortlist:
                shortlist.append(r)
            if len(shortlist) >= 3:
                break
        for r in shortlist:
            print(f"  CF solve T_air={r['T_air']} a={r['a']} p={r['P_atm']}…")
            cf = try_counterflow_steady(r["T_air"], r["P_atm"], r["a"])
            cf_results.append(dict(T_air=r["T_air"], a=r["a"], P_atm=r["P_atm"], **cf))
            print("   ", cf)
        (OUT / "counterflow_checks.json").write_text(json.dumps(cf_results, indent=2))

    # Figures
    try:
        import matplotlib.pyplot as plt

        for P in pressures:
            sub = [r for r in results if r["P_atm"] == P]
            fig, ax = plt.subplots(figsize=(7.2, 5.0))
            # scatter: color by status
            for r in sub:
                if r["comfortable"]:
                    c, m, lab = "#1e8449", "o", "comfortable"
                elif r["marginal"]:
                    c, m, lab = "#f39c12", "s", "marginal"
                elif r["ignites"]:
                    c, m, lab = "#e74c3c", "^", "ignites slow"
                else:
                    c, m, lab = "#95a5a6", "x", "no ign"
                ax.scatter(r["a"], r["T_air"], c=c, marker=m, s=80, zorder=3)
            # legend unique
            from matplotlib.lines import Line2D
            handles = [
                Line2D([0], [0], marker="o", color="w", markerfacecolor="#1e8449", ms=10, label="comfortable (τ·a≤0.5)"),
                Line2D([0], [0], marker="s", color="w", markerfacecolor="#f39c12", ms=10, label="marginal (τ·a≤1)"),
                Line2D([0], [0], marker="^", color="w", markerfacecolor="#e74c3c", ms=10, label="ignites but slow"),
                Line2D([0], [0], marker="x", color="#95a5a6", ms=10, label="no ignition"),
            ]
            ax.legend(handles=handles, fontsize=8)
            ax.set_xscale("log")
            ax.set_xlabel("strain a [1/s]")
            ax.set_ylabel("T_air [K]")
            ax.set_title(f"E18 Stage0 ignition map — p={P:g} atm (MRM 0D τ vs 1/a)")
            ax.set_yticks(T_AIR_LIST)
            ax.grid(True, which="both", alpha=0.3)
            if pick and pick["P_atm"] == P:
                ax.scatter([pick["a"]], [pick["T_air"]], s=200, facecolors="none",
                           edgecolors="k", linewidths=2, label="pick", zorder=5)
            fig.tight_layout()
            fig.savefig(OUT / f"ignition_map_p{P:g}atm.png", dpi=160)
            plt.close()
    except Exception as e:
        print("plot skipped:", e)

    # Rationale text
    rationale = []
    if pick:
        rationale.append(
            f"Production pick: p={pick['P_atm']} atm, T_air={pick['T_air']} K, "
            f"a={pick['a']} s⁻¹, τ_ign={pick['tau_ign_s']*1e3:.2f} ms, "
            f"τ_res=1/a={pick['tau_res_s']*1e3:.2f} ms, Da⁻¹=τ·a={pick['Da_inv']:.3f}, "
            f"Z*={pick['Z_star']}, Tmix*={pick['Tmix_star']:.1f} K."
        )
        if pick["T_air"] > 1000:
            rationale.append(
                f"T_air promoted above 1000 K because lower T_air points were "
                f"non-igniting or not comfortable under target strain (physics)."
            )
        if pick["P_atm"] == 10:
            rationale.append(
                "p=10 atm retained: matches OF/E12–E17 mechanism validation pressure "
                "and yields comfortable ignition at moderate strain; 1 atm only if scout requires."
            )
        elif pick["P_atm"] == 1:
            rationale.append(
                "p=1 atm selected because 10 atm scout did not yield a comfortable "
                "(a,T_air) in the requested band — check boundary table."
            )
        rationale.append(
            "Inlet velocities for 2D: a ≈ 2·V_inlet/gap (equal-momentum); "
            f"with gap L, V_inlet ≈ a·L/2."
        )
    else:
        rationale.append("NO viable point on the grid — expand T_air upward or lower a.")

    report = dict(
        campaign="E18-prep Stage0",
        method=(
            "Mixing-line most-reactive mixture (MRM) 0D const-p ignition delay "
            "vs opposed-jet residence τ_res=1/a. Comfortable: τ_ign/τ_res ≤ 0.5. "
            "Not a full transient 1D counterflow ODE; optional steady CF checks separate."
        ),
        yaml=str(YAML),
        DA_COMFORT=DA_COMFORT,
        DA_MARGINAL=DA_MARGINAL,
        grid=dict(a=A_LIST, T_air=T_AIR_LIST, P_atm=list(pressures), Z=list(map(float, Z_LIST))),
        boundary=boundary,
        pick=pick,
        rationale=rationale,
        n_comfort=len(comfort),
        counterflow_checks=cf_results,
    )
    (OUT / "STAGE0_REPORT.json").write_text(json.dumps(report, indent=2))

    md = [
        "# E18 Stage 0 — Ignition viability scout",
        "",
        f"**Method:** {report['method']}",
        f"**Mechanism:** `{YAML.name}`",
        "",
        "## Production pick",
        "",
    ]
    if pick:
        md += [
            f"| quantity | value |",
            f"|----------|-------|",
            f"| p | **{pick['P_atm']} atm** |",
            f"| T_air | **{pick['T_air']} K** |",
            f"| strain a | **{pick['a']} s⁻¹** |",
            f"| τ_ign (MRM) | {pick['tau_ign_s']*1e3:.2f} ms |",
            f"| τ_res = 1/a | {pick['tau_res_s']*1e3:.2f} ms |",
            f"| τ_ign / τ_res | {pick['Da_inv']:.3f} |",
            f"| Z\\* | {pick['Z_star']} |",
            f"| Tmix\\* | {pick['Tmix_star']:.1f} K |",
            f"| T_peak 0D | {pick['T_peak_0D']:.1f} K |",
            f"| ignition side (mix) | {pick.get('ignition_side')} |",
            "",
            "## Rationale",
            "",
        ]
        md += [f"- {line}" for line in rationale]
    else:
        md.append("**No pick** — see grid CSV.")
    md += ["", "## Ignition / no-ignition boundary (min T_air by class)", ""]
    for P, by_a in boundary.items():
        md.append(f"### p = {P} atm")
        md.append("| a [1/s] | min T comfortable | min T marginal | min T ignites |")
        md.append("|--------:|------------------:|---------------:|--------------:|")
        for a, d in by_a.items():
            md.append(
                f"| {a:g} | {d['min_T_comfortable']} | {d['min_T_marginal']} | {d['min_T_ignites']} |"
            )
        md.append("")
    md += [
        "## Files",
        "",
        "- `scout_grid.csv` — flat results",
        "- `scout_grid_full.json` — includes Z scans",
        "- `ignition_map_p*.png` — (a, T_air) maps",
        "",
        "## Next (Stage 1) — not built yet",
        "",
        "Twin-nozzle cold mixing at pick (a, T_air, p); chemistry OFF; freeze developed field.",
    ]
    (OUT / "STAGE0_REPORT.md").write_text("\n".join(md))
    print("\n=== PICK ===")
    print(json.dumps(pick, indent=2))
    print("Wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

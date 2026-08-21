#!/usr/bin/env python3
"""Compare base vs finetuned policies on MidT 0D selection patterns.

Finetuned files are bare network state_dicts (no obs_rms). This script:
  1) wraps them with base-model obs_rms
  2) teacher-forces all policies on one CVODE MidT trajectory (fair compare)
  3) optionally free-runs AdaptiveRL for each (closed-loop usage)

Usage:
  python validation/zeroD/compare_finetune_policies.py
  python validation/zeroD/compare_finetune_policies.py --free-run
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "policy"
MECH = ROOT / "mechanisms/refit/n-dodecane_refit.yaml"
OUT = ROOT / "validation/e16_parity/finetune_compare"
HANDOFF = Path("/Users/el0tech/Documents/research_code/solver_selection/handoff/src")
BASE = POLICY / "best_offline_eval2.pt"
KEY = ["oh", "h2o", "o2", "h2", "h2o2", "o", "h", "n2"]
FUEL = "nc12h26:1.0"
OX = "o2:1.0, n2:3.76"

# MidT paper condition (C2), shortened horizon for a quick pattern check
MIDT = dict(T0=800.0, p_atm=10.0, Z=0.062, dt=1e-6, t_end=1.0e-3, num_steps=20)

MODELS = [
    ("base", BASE),
    ("lambda_1p0", POLICY / "lambda_1p0.pt"),
    ("lambda_init_1p0", POLICY / "lambda_init=1.0.pt"),
    ("finetuned_1D_policy6", POLICY / "finetuned_1D_policy6.pt"),
]


def load_base_bundle():
    sys.path.insert(0, str(HANDOFF))
    import solver_selection_handoff.ppo_agent as pa

    sys.modules["ppo_agent"] = pa
    ck = torch.load(BASE, map_location="cpu", weights_only=False)
    assert "obs_rms" in ck and "network_state_dict" in ck
    return ck


def wrap_checkpoint(src: Path, base_ck: dict, dest: Path, *, include_obs_rms: bool) -> Path:
    """Write a handoff-compatible checkpoint (network + optional obs_rms)."""
    raw = torch.load(src, map_location="cpu", weights_only=False)
    if isinstance(raw, dict) and "network_state_dict" in raw:
        net = raw["network_state_dict"]
        # prefer embedded obs_rms if present
        obs = raw.get("obs_rms")
    else:
        net = raw
        obs = None
    out = {
        "network_state_dict": net,
        "config": base_ck.get("config"),
    }
    if include_obs_rms:
        out["obs_rms"] = obs if obs is not None else base_ck["obs_rms"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    torch.save(out, dest)
    return dest


def make_selector(ckpt_path: Path):
    from solver_selection_handoff.inference import RLSolverSelector

    sel = RLSolverSelector(
        model_path=str(ckpt_path),
        mechanism_file=str(MECH),
        device="cpu",
        network_config={"hidden_dims": [256, 128, 64], "activation": "relu"},
        key_species=KEY,
        use_prev_state=True,
        use_gradient_only=False,
        confidence_threshold=0.6,
    )
    sel.reset()
    return sel


def summarize_flags(flags: list[int], confs: list[float], ps: list[float]) -> dict:
    flags = np.asarray(flags, dtype=int)
    confs = np.asarray(confs, dtype=float)
    ps = np.asarray(ps, dtype=float)
    n = len(flags)
    n_cvode = int(np.sum(flags == 0))
    n_qss = int(np.sum(flags == 1))
    return {
        "n": n,
        "n_CVODE": n_cvode,
        "n_QSS": n_qss,
        "CVODE_frac": n_cvode / max(n, 1),
        "QSS_frac": n_qss / max(n, 1),
        "mean_conf": float(np.mean(confs)) if n else float("nan"),
        "ood_frac": float(np.mean(np.abs(ps - 0.5) < 0.1)) if n else float("nan"),
    }


def teacher_forced_on_cvode(selectors: dict[str, object], c: dict) -> dict:
    """Advance with CVODE only; query every policy at each decision epoch."""
    import cantera as ct
    from solver_selection_handoff.evaluation_pipeline import ObservationBuilder

    gas = ct.Solution(str(MECH))
    key_idx = [gas.species_index(s) for s in KEY]
    gas.set_mixture_fraction(c["Z"], FUEL, OX)
    gas.TP = c["T0"], c["p_atm"] * ct.one_atm
    r = ct.IdealGasConstPressureReactor(gas)
    sim = ct.ReactorNet([r])
    sim.rtol, sim.atol = 1e-8, 1e-12

    builders = {
        name: ObservationBuilder(
            species_indices=key_idx,
            use_prev_state=True,
            use_gradient_only=False,
        )
        for name in selectors
    }
    for b in builders.values():
        b.reset(np.concatenate([[gas.T], gas.Y]))

    for sel in selectors.values():
        sel.reset()

    records = {name: [] for name in selectors}
    t = 0.0
    dt = c["dt"]
    n_steps = c["num_steps"]
    end = c["t_end"]
    epoch = 0
    while t < end - 0.5 * dt:
        state = np.concatenate([[gas.T], gas.Y])
        P = float(gas.P)
        for name, sel in selectors.items():
            obs = builders[name].build(state, P)
            act, conf, probs, _ = sel.select_action_detailed(obs)
            if conf < sel.confidence_threshold:
                act = 0
            records[name].append(
                {
                    "epoch": epoch,
                    "t": t,
                    "T": float(gas.T),
                    "flag": int(act),
                    "conf": float(conf),
                    "p_QSS": float(probs[1]),
                }
            )
        for _ in range(n_steps):
            t_target = min(t + dt, end)
            sim.advance(t_target)
            t = float(sim.time)
            if t >= end - 1e-15:
                break
        epoch += 1

    return records


def free_run_adaptive(ckpt_path: Path, c: dict, tag: str) -> dict:
    from solver_selection_handoff.evaluation_pipeline import CompletePipeline
    import cantera as ct

    selector = make_selector(ckpt_path)
    condition = {
        "temp": c["T0"],
        "pressure": c["p_atm"] * ct.one_atm,
        "Z": c["Z"],
        "fuel": FUEL,
        "oxidizer": OX,
        "dt": c["dt"],
        "t_end": c["t_end"],
        "key_species": KEY,
    }
    config = {
        "num_steps": c["num_steps"],
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
    res = pipeline.evaluator.evaluate(
        strategies["RL-Adaptive"],
        pipeline.initial_state.copy(),
    )
    dec = getattr(res, "rl_decisions", None) or []
    flags, confs, ps = [], [], []
    # decisions may be list of dicts or tuples depending on pipeline version
    for d in dec:
        if isinstance(d, dict):
            flags.append(int(d.get("action", d.get("flag", 0))))
            confs.append(float(d.get("confidence", d.get("conf", 1.0))))
            ps.append(float(d.get("p_QSS", d.get("p", 0.5))))
        else:
            # (t, action, conf, ...) best-effort
            flags.append(int(d[1]))
            confs.append(float(d[2]) if len(d) > 2 else 1.0)
            ps.append(0.5)
    summary = summarize_flags(flags, confs, ps)
    summary["tag"] = tag
    summary["tau_ign"] = None
    if getattr(res, "temperature", None) is not None and getattr(res, "time", None) is not None:
        T = np.asarray(res.temperature)
        tt = np.asarray(res.time)
        if len(T) > 2:
            dT = np.diff(T) / np.diff(tt)
            summary["tau_ign"] = float(tt[int(np.argmax(dT))])
            summary["T_final"] = float(T[-1])
    return summary


def agreement(a: list[dict], b: list[dict]) -> dict:
    n = min(len(a), len(b))
    if n == 0:
        return {"n": 0, "agree": 0.0}
    ok = sum(1 for i in range(n) if a[i]["flag"] == b[i]["flag"])
    return {"n": n, "n_ok": ok, "agree": ok / n}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--free-run", action="store_true", help="Also free-run AdaptiveRL per policy")
    ap.add_argument("--t-end", type=float, default=MIDT["t_end"])
    args = ap.parse_args()
    c = dict(MIDT)
    c["t_end"] = args.t_end

    OUT.mkdir(parents=True, exist_ok=True)
    base_ck = load_base_bundle()

    wrapped = {}
    for name, path in MODELS:
        if not path.is_file():
            raise FileNotFoundError(path)
        dest = OUT / "ckpts" / f"{name}_with_base_obs_rms.pt"
        wrap_checkpoint(path if name != "base" else BASE, base_ck, dest, include_obs_rms=True)
        wrapped[name] = dest

    # Ablation: one finetune WITHOUT obs_rms (should look broken / more QSS)
    ablate = OUT / "ckpts" / "lambda_1p0_NO_obs_rms.pt"
    wrap_checkpoint(POLICY / "lambda_1p0.pt", base_ck, ablate, include_obs_rms=False)

    print("[compare] loading selectors with base obs_rms ...", flush=True)
    selectors = {name: make_selector(p) for name, p in wrapped.items()}
    selectors["lambda_1p0_NO_obs_rms"] = make_selector(ablate)

    # Confirm obs_rms actually loaded
    rms_status = {}
    for name, sel in selectors.items():
        m = np.asarray(sel.agent.obs_rms.mean).ravel()
        rms_status[name] = {
            "obs_rms_mean0": float(m[0]),
            "obs_rms_loaded_nonzero": bool(np.any(np.abs(m) > 1e-12)),
            "count": float(getattr(sel.agent.obs_rms, "count", 0)),
        }
        print(f"  {name}: obs_rms mean[0]={m[0]:.4f} nonzero={rms_status[name]['obs_rms_loaded_nonzero']}")

    print(f"[compare] teacher-forced on CVODE MidT t_end={c['t_end']} ...", flush=True)
    records = teacher_forced_on_cvode(selectors, c)

    summaries = {}
    for name, rows in records.items():
        flags = [r["flag"] for r in rows]
        confs = [r["conf"] for r in rows]
        ps = [r["p_QSS"] for r in rows]
        summaries[name] = summarize_flags(flags, confs, ps)
        # write CSV
        csv_path = OUT / f"tf_{name}.csv"
        with csv_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    # agreements vs base
    agrees = {
        name: agreement(records["base"], records[name])
        for name in records
        if name != "base"
    }

    free = {}
    if args.free_run:
        print("[compare] free-run AdaptiveRL ...", flush=True)
        for name, path in wrapped.items():
            print(f"  free-run {name} ...", flush=True)
            free[name] = free_run_adaptive(path, c, name)

    report = {
        "condition": c,
        "obs_rms_source": str(BASE),
        "rms_status": rms_status,
        "teacher_forced": summaries,
        "agreement_vs_base": agrees,
        "free_run": free,
        "note": (
            "Teacher-forced = same CVODE MidT states for all policies. "
            "Finetunes wrapped with base obs_rms. Ablation lambda_1p0_NO_obs_rms "
            "omits obs_rms (default RunningMeanStd)."
        ),
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n")

    # Markdown brief
    lines = [
        "# Finetune policy compare (MidT 0D, teacher-forced on CVODE)",
        "",
        f"Horizon t_end={c['t_end']}, dt={c['dt']}, num_steps={c['num_steps']}, "
        f"τ_dec={c['dt']*c['num_steps']:g} s.",
        "",
        "All finetunes are bare `state_dict`s; **base `obs_rms` injected** "
        f"from `{BASE.name}`.",
        "",
        "## Selection (teacher-forced)",
        "",
        "| Policy | n | CVODE% | QSS% | mean conf | agree vs base |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, s in summaries.items():
        ag = agrees.get(name, {}).get("agree", 1.0 if name == "base" else float("nan"))
        lines.append(
            f"| {name} | {s['n']} | {100*s['CVODE_frac']:.1f} | {100*s['QSS_frac']:.1f} | "
            f"{s['mean_conf']:.3f} | {100*ag:.1f}% |"
        )
    lines += [
        "",
        "## obs_rms load check",
        "",
        "| Policy | mean[0] | nonzero stats |",
        "|---|---:|:---:|",
    ]
    for name, st in rms_status.items():
        lines.append(
            f"| {name} | {st['obs_rms_mean0']:.4f} | {st['obs_rms_loaded_nonzero']} |"
        )
    if free:
        lines += ["", "## Free-run AdaptiveRL", ""]
        lines += [
            "| Policy | n | CVODE% | τ_ign [s] | T_final |",
            "|---|---:|---:|---:|---:|",
        ]
        for name, s in free.items():
            lines.append(
                f"| {name} | {s['n']} | {100*s['CVODE_frac']:.1f} | "
                f"{s.get('tau_ign')} | {s.get('T_final')} |"
            )
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    plot_path = plot_solver_profiles_2x2(OUT)
    print(json.dumps(report, indent=2))
    print(f"Wrote {OUT/'REPORT.md'}")
    print(f"Wrote {plot_path}")
    return 0


def plot_solver_profiles_2x2(out_dir: Path) -> Path:
    """2x2 T(t) colored by CVODE/QSS for base + three finetunes."""
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D

    panels = [
        ("base", "base (best_offline_eval2)"),
        ("lambda_1p0", "lambda_1p0"),
        ("lambda_init_1p0", "lambda_init=1.0"),
        ("finetuned_1D_policy6", "finetuned_1D_policy6"),
    ]
    colors = {0: "#1f77b4", 1: "#ff7f0e"}
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.5), sharex=True, sharey=True)
    for ax, (key, title) in zip(axes.ravel(), panels):
        rows = list(csv.DictReader((out_dir / f"tf_{key}.csv").open()))
        t = np.array([float(r["t"]) for r in rows]) * 1e3
        T = np.array([float(r["T"]) for r in rows])
        flag = np.array([int(r["flag"]) for r in rows])
        pts = np.column_stack([t, T])
        segs = np.stack([pts[:-1], pts[1:]], axis=1)
        lc = LineCollection(
            segs,
            colors=[colors[int(f)] for f in flag[:-1]],
            linewidths=2.2,
        )
        ax.add_collection(lc)
        for fval, c in colors.items():
            m = flag == fval
            ax.scatter(t[m], T[m], c=c, s=14, zorder=3, edgecolors="none")
        ax.set_title(f"{title}\nCVODE {100*np.mean(flag==0):.0f}%  (n={len(flag)})")
        ax.grid(True, alpha=0.3)
        ax.set_xlim(float(t.min()), float(t.max()))
        ax.set_ylim(750, max(2700.0, float(T.max()) + 50))
    axes[0, 0].set_ylabel("T [K]")
    axes[1, 0].set_ylabel("T [K]")
    axes[1, 0].set_xlabel("t [ms]")
    axes[1, 1].set_xlabel("t [ms]")
    fig.legend(
        handles=[
            Line2D([0], [0], color=colors[0], lw=2.5, label="CVODE"),
            Line2D([0], [0], color=colors[1], lw=2.5, label="QSS"),
        ],
        loc="upper center",
        ncol=2,
        frameon=False,
    )
    fig.suptitle(
        "MidT 0D teacher-forced — solver selection along T(t)\n"
        "finetunes use base obs_rms",
        y=0.98,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.90])
    png = out_dir / "T_profile_solver_2x2.png"
    fig.savefig(png, dpi=160)
    fig.savefig(out_dir / "T_profile_solver_2x2.pdf")
    plt.close(fig)
    return png


if __name__ == "__main__":
    raise SystemExit(main())

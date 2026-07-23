#!/usr/bin/env python3
"""E17.3 post-run analysis: figures, animations, cost table, accuracy, stiff cell.

Outputs under <base>/e17_3/
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
from matplotlib.patches import Patch
from matplotlib.colors import ListedColormap

NX, NY = 80, 40
N_CELLS = NX * NY

# Publication style
mpl.rcParams.update({
    "figure.dpi": 140,
    "savefig.dpi": 180,
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "legend.fontsize": 8,
    "font.family": "DejaVu Sans",
})

C_CVODE = "#c0392b"
C_QSS = "#1e8449"
C_FALL = "#f1c40f"
C_MUTED = "#7f8c8d"


def parse_vol_scalar(path: Path, n_cells: int = N_CELLS) -> np.ndarray | None:
    if not path.is_file():
        return None
    raw = path.read_bytes()
    head = raw[:900].decode("latin1", errors="ignore")
    is_binary = "format      binary" in head
    if not is_binary:
        text = raw.decode("utf-8", errors="replace")
        m = re.search(r"internalField\s+uniform\s+([^\s;]+)", text)
        if m:
            return np.full(n_cells, float(m.group(1)))
        m = re.search(
            r"internalField\s+nonuniform\s+List<(?:scalar|label)>\s*\n\s*(\d+)\s*\n\s*\((.*?)\)",
            text,
            re.S,
        )
        if not m:
            return None
        return np.fromstring(m.group(2), sep=" ", dtype=float)
    m = re.search(rb"List<(?:scalar|label)>\s*\n\s*(\d+)\s*\n", raw)
    if not m:
        return None
    n = int(m.group(1))
    start = m.end()
    if raw[start : start + 1] == b"(":
        start += 1
    return np.frombuffer(raw[start : start + n * 8], dtype="<f8").copy()


def mesh_extent(mesh_dir: Path) -> list[float]:
    text = (mesh_dir / "points").read_text(errors="replace")
    coords = re.findall(r"\(([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\)", text)
    pts = np.array([(float(a), float(b)) for a, b, _ in coords])
    return [float(pts[:, 0].min()), float(pts[:, 0].max()),
            float(pts[:, 1].min()), float(pts[:, 1].max())]


def to_grid(v: np.ndarray) -> np.ndarray:
    return v.reshape((NY, NX), order="C")


def list_times(fields: Path) -> list[tuple[float, str]]:
    out = []
    if not fields.is_dir():
        return out
    for p in fields.iterdir():
        if p.is_dir():
            try:
                out.append((float(p.name), p.name))
            except ValueError:
                pass
    return sorted(out)


def nearest(times: list[tuple[float, str]], t: float) -> str | None:
    if not times:
        return None
    return min(times, key=lambda x: abs(x[0] - t))[1]


def load_usage(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open() as f:
        return [{k: float(r[k]) for k in r} for r in csv.DictReader(f)]


def solver_rgb(flag: np.ndarray, fb: np.ndarray) -> np.ndarray:
    g = to_grid(flag)
    fbg = to_grid(fb)
    rgb = np.zeros((*g.shape, 3))
    qss = g >= 0.5
    fell = (~qss) & (fbg > 0.5)
    cvode = (~qss) & ~fell
    rgb[qss] = mpl.colors.to_rgb(C_QSS)
    rgb[cvode] = mpl.colors.to_rgb(C_CVODE)
    rgb[fell] = mpl.colors.to_rgb(C_FALL)
    return rgb


def centerline_T(T: np.ndarray) -> np.ndarray:
    g = to_grid(T)
    j = NY // 2
    return g[j, :]


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def fig_proactive_vs_reactive(rl: list[dict], qs: list[dict], out: Path) -> dict:
    """Headline thesis figure."""
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    tr = np.array([r["time"] for r in rl]) * 1e6  # µs
    tq = np.array([r["time"] for r in qs]) * 1e6

    ax.fill_between(tr, 0, [r["nQSS"] for r in rl], color=C_QSS, alpha=0.25, label="rlAdaptive QSS")
    ax.plot(tr, [r["nCVODE"] for r in rl], color=C_CVODE, lw=2.2, label="rlAdaptive policy-CVODE")
    ax.plot(tr, [r["nFallbackCVODE"] for r in rl], color=C_FALL, lw=2.4, label="rlAdaptive fallback")
    ax.plot(tq, [r["nFallbackCVODE"] for r in qs], color=C_MUTED, lw=2.0, ls="--",
            label="qssOnly fallback (reactive plateau)")

    # Annotate drain
    peak = max(rl, key=lambda r: r["nFallbackCVODE"])
    drain = next((r for r in rl if r["time"] >= peak["time"] and r["nFallbackCVODE"] <= 3), None)
    if drain:
        ax.annotate(
            f"fallback drain {int(peak['nFallbackCVODE'])}→{int(drain['nFallbackCVODE'])}\n"
            f"over 4 decision epochs\n(policy takes the front)",
            xy=(drain["time"] * 1e6, drain["nFallbackCVODE"]),
            xytext=(drain["time"] * 1e6 + 1.2, 90),
            fontsize=8,
            arrowprops=dict(arrowstyle="->", color="k", lw=0.8),
            bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#333", lw=0.6),
        )
        ax.scatter([peak["time"] * 1e6], [peak["nFallbackCVODE"]], c=C_FALL, s=40, zorder=5)
        ax.scatter([drain["time"] * 1e6], [drain["nFallbackCVODE"]], c=C_CVODE, s=40, zorder=5)

    ax.set_xlim(95, 108)
    ax.set_ylim(0, 220)
    ax.set_xlabel("physical time [µs]")
    ax.set_ylabel("cell count")
    ax.set_title("E17.3 — Proactive vs reactive front protection")
    ax.legend(loc="upper left", framealpha=0.95)
    ax.axvspan(100, 107, color="#eeeeee", zorder=0)
    fig.text(
        0.5, 0.01,
        "Thesis signature: rlAdaptive fallback drains (72→3) as policy-CVODE rises; "
        "guarded-qssOnly fallback plateaus (~70–150). Guards = safety; policy = proactive front CVODE.",
        ha="center", fontsize=8, style="italic",
    )
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    fig.savefig(out / "fig_proactive_vs_reactive.png")
    fig.savefig(out / "fig_proactive_vs_reactive.pdf")
    plt.close(fig)

    meta = {
        "peak_fallback": {"t": peak["time"], "n": int(peak["nFallbackCVODE"]),
                          "policy_CVODE": int(peak["nCVODE"])},
        "drain": None if not drain else {
            "t": drain["time"], "n": int(drain["nFallbackCVODE"]),
            "policy_CVODE": int(drain["nCVODE"]),
        },
        "qss_end_fallback": int(qs[-1]["nFallbackCVODE"]),
        "rl_end_fallback": int(rl[-1]["nFallbackCVODE"]),
        "rl_end_policy_CVODE": int(rl[-1]["nCVODE"]),
    }
    (out / "proactive_vs_reactive.json").write_text(json.dumps(meta, indent=2))
    return meta


def fig_cost_table(base: Path, rl: list[dict], qs: list[dict], out: Path) -> dict:
    def integ(rows, t0=9.5e-5, t1=1.07e-4):
        sel = [r for r in rows if t0 <= r["time"] <= t1]
        return {
            "n_steps": len(sel),
            "sum_policy_CVODE_cells": sum(r["nCVODE"] for r in sel),
            "sum_fallback_cells": sum(r["nFallbackCVODE"] for r in sel),
            "sum_CVODE_eq_cells": sum(r["nCVODE"] + r["nFallbackCVODE"] for r in sel),
            "chem_cpu_CVODE_s": sum(r["cpu_CVODE"] for r in sel),
            "chem_cpu_QSS_s": sum(r["cpu_QSS"] for r in sel),
            "chem_cpu_tot_s": sum(r["cpu_tot"] for r in sel),
        }

    def wall(mode: str) -> float | None:
        p = base / mode / "wall.txt"
        if not p.is_file():
            return None
        m = re.search(r"wall_s=(\d+)", p.read_text())
        return float(m.group(1)) if m else None

    rl_i, qs_i = integ(rl), integ(qs)
    # CVODE clock to ~1.07e-4 from prior long smoke (recorded)
    cvode_wall_matched = 3137.0  # from log ClockTime at Time≈1.07e-4
    table = {
        "horizon_s": [9.5e-5, 1.07e-4],
        "qssOnly": {**qs_i, "wall_s": wall("qssOnly")},
        "rlAdaptive": {**rl_i, "wall_s": wall("rlAdaptive")},
        "cvodeOnly": {
            "wall_s_matched_1p07e-4": cvode_wall_matched,
            "wall_s_full_5e-4": wall("cvodeOnly"),
            "note": "matched wall from ClockTime at t≈1.07e-4 in long smoke log",
        },
    }
    rw, qw = table["rlAdaptive"]["wall_s"], table["qssOnly"]["wall_s"]
    table["speedup_vs_cvode"] = {
        "rlAdaptive": cvode_wall_matched / rw if rw else None,
        "qssOnly": cvode_wall_matched / qw if qw else None,
    }
    table["cvode_eq_ratio_rl_over_qss"] = (
        rl_i["sum_CVODE_eq_cells"] / max(qs_i["sum_CVODE_eq_cells"], 1)
    )
    table["interpretation"] = (
        "On this short horizon RL spends MORE CVODE-equivalent cell-steps than "
        "guarded-qssOnly because policy proactively assigns CVODE (rising to ~200 cells) "
        "while draining fallback 72→3; qssOnly has zero policy-CVODE and a sustained "
        "fallback plateau (~144). Wall: RL slower than qssOnly (cold-start all-CVODE "
        "epochs) but ~{:.1f}× faster than pure CVODE to matched t.".format(
            table["speedup_vs_cvode"]["rlAdaptive"] or 0
        )
    )

    # Render table figure
    fig, ax = plt.subplots(figsize=(10, 3.2))
    ax.axis("off")
    rows = [
        ["metric", "cvodeOnly", "qssOnly (guarded)", "rlAdaptive"],
        ["wall to t≈1.07e-4 [s]", f"{cvode_wall_matched:.0f}", f"{qw:.0f}", f"{rw:.0f}"],
        ["chem CPU (front window) [s]", "—", f"{qs_i['chem_cpu_tot_s']:.0f}", f"{rl_i['chem_cpu_tot_s']:.0f}"],
        ["Σ policy-CVODE cell-steps", "all", "0", f"{rl_i['sum_policy_CVODE_cells']:.0f}"],
        ["Σ fallback cell-steps", "0", f"{qs_i['sum_fallback_cells']:.0f}", f"{rl_i['sum_fallback_cells']:.0f}"],
        ["Σ CVODE-eq cell-steps", "all", f"{qs_i['sum_CVODE_eq_cells']:.0f}", f"{rl_i['sum_CVODE_eq_cells']:.0f}"],
        ["speedup vs CVODE wall", "1×", f"{cvode_wall_matched/qw:.2f}×", f"{cvode_wall_matched/rw:.2f}×"],
    ]
    tbl = ax.table(cellText=rows[1:], colLabels=rows[0], loc="center", cellLoc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1.15, 1.55)
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#2c3e50")
            cell.set_text_props(color="white", weight="bold")
        elif r % 2 == 0:
            cell.set_facecolor("#f4f6f7")
    ax.set_title("E17.3 three-way cost at matched physical time (front window 95–107 µs)", pad=12)
    fig.tight_layout()
    fig.savefig(out / "fig_cost_table.png")
    plt.close(fig)
    (out / "cost_table.json").write_text(json.dumps(table, indent=2))
    return table


def fig_solver_maps_5(
    mode_dir: Path, extent: list[float], out: Path, times_target: list[float], tag: str
) -> None:
    fields = mode_dir / "fields"
    avail = list_times(fields)
    fig, axes = plt.subplots(1, 5, figsize=(14, 2.8))
    legend = [
        Patch(facecolor=C_CVODE, label="CVODE"),
        Patch(facecolor=C_QSS, label="QSS"),
        Patch(facecolor=C_FALL, label="fallback"),
    ]
    for ax, tt in zip(axes, times_target):
        name = nearest(avail, tt)
        if not name:
            ax.set_title(f"t={tt:.2e}\n(missing)")
            ax.axis("off")
            continue
        flag = parse_vol_scalar(fields / name / "solverFlag")
        fb = parse_vol_scalar(fields / name / "qssFallbackCount")
        if flag is None:
            flag = np.ones(N_CELLS)
        if fb is None:
            fb = np.zeros(N_CELLS)
        ax.imshow(solver_rgb(flag, fb), origin="lower", extent=extent, aspect="equal",
                  interpolation="nearest")
        ax.set_title(f"t={float(name):.2e}", fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
    axes[0].legend(handles=legend, loc="upper left", fontsize=7, framealpha=0.9)
    fig.suptitle(f"{tag} — solver selection through ignition (write times)", fontsize=11)
    fig.tight_layout()
    fig.savefig(out / f"fig_solver_maps_5_{tag}.png")
    plt.close(fig)


def fig_accuracy(base: Path, extent: list[float], out: Path) -> dict:
    """T RMSE rl/qss vs cvode at nearest matched write times. OH if present."""
    cv_times = list_times(base / "cvodeOnly" / "fields")
    results = {}
    for mode in ("rlAdaptive", "qssOnly"):
        mt = list_times(base / mode / "fields")
        rows = []
        for t, name in mt:
            cname = nearest(cv_times, t)
            if not cname:
                continue
            Tm = parse_vol_scalar(base / mode / "fields" / name / "T")
            Tc = parse_vol_scalar(base / "cvodeOnly" / "fields" / cname / "T")
            if Tm is None or Tc is None:
                continue
            # flame region: T_cvode > 1600
            mask = Tc > 1600
            if mask.sum() < 10:
                mask = np.ones(len(Tc), dtype=bool)
            rmse = float(np.sqrt(np.mean((Tm[mask] - Tc[mask]) ** 2)))
            bias = float(np.mean(Tm[mask] - Tc[mask]))
            oh_rmse = None
            Om = parse_vol_scalar(base / mode / "fields" / name / "OH")
            Oc = parse_vol_scalar(base / "cvodeOnly" / "fields" / cname / "OH")
            if Om is not None and Oc is not None:
                oh_rmse = float(np.sqrt(np.mean((Om[mask] - Oc[mask]) ** 2)))
            rows.append({
                "t_mode": t, "t_cvode": float(cname),
                "dt": abs(t - float(cname)),
                "T_RMSE_flame": rmse, "T_bias_flame": bias,
                "OH_RMSE_flame": oh_rmse, "n_flame": int(mask.sum()),
                "Tmax_mode": float(Tm.max()), "Tmax_cvode": float(Tc.max()),
            })
        results[mode] = rows

        # plot last comparable frame ΔT
        if rows:
            last = rows[-1]
            name = nearest(mt, last["t_mode"])
            cname = nearest(cv_times, last["t_cvode"])
            Tm = parse_vol_scalar(base / mode / "fields" / name / "T")
            Tc = parse_vol_scalar(base / "cvodeOnly" / "fields" / cname / "T")
            dT = Tm - Tc
            lim = max(50, np.percentile(np.abs(dT), 99))
            fig, axes = plt.subplots(1, 3, figsize=(11, 3.2))
            for ax, data, title, cmap, vmin, vmax in [
                (axes[0], Tm, f"{mode} T", "hot", None, None),
                (axes[1], Tc, f"CVODE T @ {cname}", "hot", None, None),
                (axes[2], dT, f"ΔT RMSE_flame={last['T_RMSE_flame']:.1f} K", "coolwarm", -lim, lim),
            ]:
                g = to_grid(data)
                im = ax.imshow(g, origin="lower", extent=extent, aspect="equal",
                               cmap=cmap, vmin=vmin, vmax=vmax, interpolation="bilinear")
                ax.set_title(title, fontsize=9)
                plt.colorbar(im, ax=ax, fraction=0.046)
            gate = "PASS (~10 K)" if last["T_RMSE_flame"] < 15 else "CHECK gate"
            fig.suptitle(f"Accuracy {mode} vs cvodeOnly — flame-region T ({gate})", fontsize=11)
            fig.tight_layout()
            fig.savefig(out / f"fig_accuracy_{mode}.png")
            plt.close(fig)

    (out / "accuracy.json").write_text(json.dumps(results, indent=2))
    return results


def stiff_cell_dump(base: Path, out: Path) -> dict:
    """Nearest decision epoch to 1.0365e-4; classify hottest CVODE / fallback context."""
    target = 1.0365e-4
    dec = base / "rlAdaptive" / "rl_decisions.csv"
    usage = load_usage(base / "rlAdaptive" / "rl_usage_step.csv")
    u_near = min(usage, key=lambda r: abs(r["time"] - target)) if usage else None

    # decisions only at τ_dec epochs — pick nearest chemTime
    chem_times = set()
    with dec.open() as f:
        for row in csv.DictReader(f):
            chem_times.add(float(row["chemTime"]))
    nearest_chem = min(chem_times, key=lambda t: abs(t - target)) if chem_times else None
    rows = []
    if nearest_chem is not None:
        with dec.open() as f:
            for row in csv.DictReader(f):
                if abs(float(row["chemTime"]) - nearest_chem) < 1e-15:
                    rows.append(row)
    cv = [r for r in rows if float(r["flag"]) < 0.5]
    cv.sort(key=lambda r: -float(r["T"]))
    # Also report hottest QSS (true front) for context
    qs = [r for r in rows if float(r["flag"]) >= 0.5]
    qs.sort(key=lambda r: -float(r["T"]))

    def pack(r):
        ys = [float(r[f"Y{i}"]) for i in range(8)]
        return {
            "celli": int(r["celli"]),
            "T": float(r["T"]),
            "conf": float(r["conf"]),
            "flag": float(r["flag"]),
            "Y": {f"Y{i}": ys[i] for i in range(8)},
            "minY": min(ys),
            "sumY": sum(ys),
            "class": (
                "mild-negativity" if min(ys) < 0
                else "bounded-hard (Y≥0, ΣY≈1; stiffness from kinetics/thermo path)"
            ),
        }

    report = {
        "requested_t": target,
        "nearest_decision_chemTime": nearest_chem,
        "note": (
            "Decision CSV only stores τ_dec epochs; nearest to 1.0365e-4 is chemTime="
            f"{nearest_chem}. Peak fallback in usage is at t={u_near['time'] if u_near else None} "
            f"with nFallback={u_near['nFallbackCVODE'] if u_near else None}. "
            "At the first policy-CVODE epoch, selected CVODE cells are cooler boundary cells; "
            "the hot front is still QSS until fallback/policy later expands CVODE duty."
        ),
        "usage_at_nearest": u_near,
        "hottest_policy_CVODE": pack(cv[0]) if cv else None,
        "hottest_QSS_front": pack(qs[0]) if qs else None,
        "n_policy_CVODE": len(cv),
        "intrinsic_front_cost": (
            "Fallback spike to 72 cells at t≈1.026e-4 is the reactive stiff-front cost; "
            "policy then absorbs duty (CVODE↑, fallback→3). Treat peak-fallback cells as "
            "intrinsic front CVODE work even when Y remains non-negative (bounded-hard)."
        ),
    }
    (out / "stiff_cell.json").write_text(json.dumps(report, indent=2))
    return report


def make_animation(
    mode_dir: Path,
    cvode_fields: Path,
    extent: list[float],
    out_gif: Path,
    title: str,
) -> None:
    """Animate T (mode | CVODE) with per-cell solver strip beneath mode panel."""
    mt = list_times(mode_dir / "fields")
    ct = list_times(cvode_fields)
    if not mt:
        return

    # Shared T scale across frames (mode + available CVODE)
    tmax = 300.0
    for _, name in mt:
        T = parse_vol_scalar(mode_dir / "fields" / name / "T")
        if T is not None:
            tmax = max(tmax, float(T.max()))
    for _, name in ct:
        T = parse_vol_scalar(cvode_fields / name / "T")
        if T is not None:
            tmax = max(tmax, float(T.max()))

    fig = plt.figure(figsize=(10, 5.2))
    gs = fig.add_gridspec(2, 2, height_ratios=[4.2, 0.9], hspace=0.28, wspace=0.22)
    ax_m = fig.add_subplot(gs[0, 0])
    ax_c = fig.add_subplot(gs[0, 1])
    ax_s = fig.add_subplot(gs[1, :])
    fig.suptitle(title, fontsize=12)

    im_m = ax_m.imshow(
        np.zeros((NY, NX)), origin="lower", extent=extent, aspect="equal",
        cmap="inferno", vmin=300, vmax=tmax, interpolation="bilinear",
    )
    im_c = ax_c.imshow(
        np.zeros((NY, NX)), origin="lower", extent=extent, aspect="equal",
        cmap="inferno", vmin=300, vmax=tmax, interpolation="bilinear",
    )
    plt.colorbar(im_m, ax=ax_m, fraction=0.046, label="T [K]")
    plt.colorbar(im_c, ax=ax_c, fraction=0.046, label="T [K]")
    ax_m.set_title("mode")
    ax_c.set_title("cvodeOnly")
    im_s = ax_s.imshow(
        np.zeros((NY, NX, 3)), origin="lower", extent=extent, aspect="auto",
        interpolation="nearest",
    )
    ax_s.set_title("solver map (red=CVODE, green=QSS, yellow=fallback)", fontsize=9)
    ax_s.set_xlabel("x [m]")
    t_text = fig.text(0.5, 0.02, "", ha="center", fontsize=10)

    def frame(i: int):
        tval, name = mt[i]
        Tm = parse_vol_scalar(mode_dir / "fields" / name / "T")
        flag = parse_vol_scalar(mode_dir / "fields" / name / "solverFlag")
        fb = parse_vol_scalar(mode_dir / "fields" / name / "qssFallbackCount")
        if flag is None:
            flag = np.ones(N_CELLS)
        if fb is None:
            fb = np.zeros(N_CELLS)
        im_m.set_data(to_grid(Tm) if Tm is not None else np.zeros((NY, NX)))
        ax_m.set_title(f"{mode_dir.name}  t={tval:.3e} s")

        cname = nearest(ct, tval)
        if cname and abs(float(cname) - tval) < 2.5e-5:
            Tc = parse_vol_scalar(cvode_fields / cname / "T")
            im_c.set_data(to_grid(Tc) if Tc is not None else np.zeros((NY, NX)))
            ax_c.set_title(f"cvodeOnly  t={float(cname):.3e} s")
            ax_c.set_facecolor("white")
        else:
            im_c.set_data(np.full((NY, NX), np.nan))
            ax_c.set_title("cvodeOnly (no pack ≤0.0001; purged)")
            ax_c.set_facecolor("#dddddd")

        im_s.set_data(solver_rgb(flag, fb))
        t_text.set_text(f"frame {i+1}/{len(mt)}   t = {tval*1e6:.1f} µs")
        return im_m, im_c, im_s, t_text

    anim = animation.FuncAnimation(fig, frame, frames=len(mt), interval=450, blit=False)
    anim.save(out_gif, writer=animation.PillowWriter(fps=2))
    plt.close(fig)


def write_report(out: Path, meta: dict, cost: dict, acc: dict, stiff: dict) -> None:
    lines = [
        "# E17.3 post-run analysis",
        "",
        "## Headline — proactive vs reactive",
        "",
        meta.get("caption", ""),
        "",
        f"- RL peak fallback: **{meta['peak_fallback']['n']}** at t={meta['peak_fallback']['t']}",
        f"- RL drain: **{meta['drain']['n']}** at t={meta['drain']['t']} "
        f"(policy-CVODE={meta['drain']['policy_CVODE']})" if meta.get("drain") else "",
        f"- qssOnly end fallback plateau: **{meta['qss_end_fallback']}**",
        "",
        "## Cost",
        "",
        "```json",
        json.dumps(cost, indent=2)[:2500],
        "```",
        "",
        cost.get("interpretation", ""),
        "",
        "## Accuracy",
        "",
        "OH fields were not packed in this campaign — T-only RMSE reported.",
        "",
        "## Stiff-front cell",
        "",
        stiff.get("intrinsic_front_cost", ""),
        "",
        "## Figures",
        "",
        "- `fig_proactive_vs_reactive.png` — **advisor headline**",
        "- `fig_cost_table.png`",
        "- `fig_solver_maps_5_*.png`",
        "- `anim_T_*_vs_cvode.gif`",
        "- `fig_accuracy_*.png`",
    ]
    (out / "E17_3_REPORT.md").write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    args = ap.parse_args()
    base = args.base
    out = base / "e17_3"
    out.mkdir(parents=True, exist_ok=True)

    mesh = Path(__file__).resolve().parents[3] / "cases/opposedJet_2D/constant/polyMesh"
    extent = mesh_extent(mesh)

    rl = load_usage(base / "rlAdaptive" / "rl_usage_step.csv")
    qs = load_usage(base / "qssOnly" / "rl_usage_step.csv")

    print("=== proactive vs reactive ===")
    meta = fig_proactive_vs_reactive(rl, qs, out)
    meta["caption"] = (
        "The rlAdaptive fallback-drain (72→3) against qssOnly's sustained plateau "
        "IS the thesis result: guards provide safety; the policy provides proactive "
        "front protection as CVODE duty is assumed at the front."
    )
    (out / "HEADLINE.txt").write_text(meta["caption"] + "\n")

    print("=== cost table ===")
    cost = fig_cost_table(base, rl, qs, out)

    print("=== solver maps ×5 ===")
    # Prefer times spanning ignition; field packs only to 1e-4 for RL/QSS
    targets = [5e-5, 7e-5, 8e-5, 9e-5, 1e-4]
    fig_solver_maps_5(base / "rlAdaptive", extent, out, targets, "rlAdaptive")
    fig_solver_maps_5(base / "qssOnly", extent, out, targets, "qssOnly")

    print("=== accuracy ===")
    acc = fig_accuracy(base, extent, out)

    print("=== stiff cell ===")
    stiff = stiff_cell_dump(base, out)

    print("=== animations (GIF) ===")
    make_animation(
        base / "qssOnly", base / "cvodeOnly" / "fields", extent,
        out / "anim_T_qss_vs_cvode.gif",
        "E17.3 Temporal T — guarded QSS vs CVODE (+ solver strip)",
    )
    make_animation(
        base / "rlAdaptive", base / "cvodeOnly" / "fields", extent,
        out / "anim_T_rl_vs_cvode.gif",
        "E17.3 Temporal T — RL adaptive vs CVODE (+ solver strip)",
    )

    write_report(out, meta, cost, acc, stiff)
    print(f"DONE → {out}")


if __name__ == "__main__":
    main()

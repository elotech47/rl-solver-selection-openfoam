"""
Publication-style comparison figures for 0-D reactor evaluation.

Produces a 3×2 panel per condition:
  temperature | species₁
  species₂    | species₃
  solver strip | ignition delay + CPU bars
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec
from matplotlib.patches import Patch

from .io_utils import TIMING_STATS_KEY, get_cpu_mean_std
from .metrics import ignition_delay_s, primary_solver

LINE_CFG = {
    "CVODE":         {"color": "black",   "lw": 4.0, "ls": "-",  "alpha": 0.90},
    "QSS":           {"color": "blue",    "lw": 3.5, "ls": "--", "alpha": 0.85},
    "RL-Adaptive":   {"color": "orange",  "lw": 3.5, "ls": "--", "alpha": 0.90},
    "Supervised-ML": {"color": "#9467bd", "lw": 3.0, "ls": ":",  "alpha": 0.85},
}

BAR_COLORS = {
    "CVODE":         "#1f77b4",
    "QSS":           "#ff7f0e",
    "RL-Adaptive":   "#d62728",
    "Supervised-ML": "#9467bd",
}

SHORT_LABELS = {
    "CVODE": "CVODE",
    "QSS": "QSS",
    "RL-Adaptive": "RL",
    "Supervised-ML": "Sup-ML",
}

ADAPTIVE_ORDER = ("RL-Adaptive", "Supervised-ML")


def _format_species(name: str) -> str:
    return re.sub(r"([A-Za-z]+)(\d+)", r"\1$_{\2}$", name)


def _style_axis(ax) -> None:
    ax.set_facecolor("white")
    ax.grid(True, alpha=0.3, linestyle="-", linewidth=1.0, color="gray")
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", labelsize=18, width=2.0, length=8)
    for spine in ax.spines.values():
        spine.set_linewidth(3.0)
        spine.set_edgecolor("black")
        spine.set_zorder(10)


def plot_condition_comparison(
    results: dict,
    *,
    temp: float,
    pressure_atm: float,
    dt: float,
    outdir: Path,
    gas,
    species_to_plot: Sequence[str],
    methods: Optional[Sequence[str]] = None,
    title: Optional[str] = None,
    formats: Sequence[str] = ("png", "pdf"),
    dpi: int = 300,
) -> List[Path]:
    """
    Write comparison figure(s) for one condition.

    Returns list of saved paths.
    """
    plot_order = list(
        methods
        or ["CVODE", "QSS", "RL-Adaptive", "Supervised-ML"]
    )
    # Keep only methods with trajectories.
    plot_order = [
        m for m in plot_order
        if m in results
        and getattr(results[m], "trajectory", None) is not None
    ]

    species_idx: Dict[str, int] = {}
    for sp in species_to_plot:
        try:
            species_idx[sp] = gas.species_index(sp) + 1
        except Exception:
            # Species missing from this mechanism — skip in species panels.
            continue
    species_ok = [sp for sp in species_to_plot if sp in species_idx]

    fig = plt.figure(figsize=(20, 22), dpi=dpi)
    fig.patch.set_facecolor("white")
    gs = GridSpec(3, 2, figure=fig, hspace=0.38, wspace=0.32, height_ratios=[1, 1, 0.55])

    def times_ms(r):
        return np.asarray(r.times) * 1e3

    # ---- Temperature ----
    ax_temp = fig.add_subplot(gs[0, 0])
    _style_axis(ax_temp)
    for zi, mname in enumerate(plot_order):
        r = results[mname]
        cfg = LINE_CFG.get(mname, {"color": "gray", "lw": 2.5, "ls": "-", "alpha": 0.85})
        ax_temp.plot(
            times_ms(r), r.trajectory[:, 0],
            color=cfg["color"], linewidth=cfg["lw"], linestyle=cfg["ls"],
            label=mname, alpha=cfg["alpha"], zorder=2 + zi,
        )
    ax_temp.set_xlabel("Time (ms)", fontsize=22, fontweight="bold")
    ax_temp.set_ylabel("Temperature (K)", fontsize=22, fontweight="bold")
    ax_temp.set_title("Temperature", fontsize=26, fontweight="bold", pad=15)
    ax_temp.legend(
        loc="best", fontsize=14, framealpha=0.95, edgecolor="black", frameon=True
    )

    # ---- Species panels (up to 3) ----
    positions = [(0, 1), (1, 0), (1, 1)]
    for i, (sp_name, (sr, sc)) in enumerate(zip(species_ok[:3], positions)):
        ax_sp = fig.add_subplot(gs[sr, sc])
        _style_axis(ax_sp)
        cidx = species_idx[sp_name]
        sp_fmt = _format_species(sp_name)
        for zi, mname in enumerate(plot_order):
            r = results[mname]
            cfg = LINE_CFG.get(
                mname, {"color": "gray", "lw": 2.5, "ls": "-", "alpha": 0.85}
            )
            ax_sp.plot(
                times_ms(r),
                np.log10(np.maximum(r.trajectory[:, cidx], 1e-16)),
                color=cfg["color"], linewidth=cfg["lw"], linestyle=cfg["ls"],
                label=mname, alpha=cfg["alpha"], zorder=2 + zi,
            )
        ax_sp.set_xlabel("Time (ms)", fontsize=22, fontweight="bold")
        ax_sp.set_ylabel(f"{sp_fmt} Mass Fraction", fontsize=22, fontweight="bold")
        ax_sp.set_title(sp_fmt, fontsize=26, fontweight="bold", pad=15)
        ax_sp.legend(
            loc="best", fontsize=14, framealpha=0.95, edgecolor="black", frameon=True
        )

    # Fill unused species slots if fewer than 3 available.
    for j in range(len(species_ok), 3):
        sr, sc = positions[j]
        ax_empty = fig.add_subplot(gs[sr, sc])
        ax_empty.axis("off")

    # ---- Solver strips ----
    ax_strip = fig.add_subplot(gs[2, 0])
    ax_strip.set_facecolor("white")
    adaptive_data = []
    adaptive_labels = []
    max_t_ms = 0.0
    for method_key in ADAPTIVE_ORDER:
        if method_key not in plot_order:
            continue
        r = results[method_key]
        seq = r.solver_sequence or []
        t_ms = np.asarray(r.times[:-1]) * 1e3
        nm = min(len(seq), len(t_ms))
        if nm == 0:
            continue
        numeric = np.array(
            [0 if primary_solver(s) == "CVODE" else 1 for s in seq[:nm]]
        )
        adaptive_data.append((t_ms[:nm], numeric))
        adaptive_labels.append(method_key)
        max_t_ms = max(max_t_ms, float(t_ms[nm - 1]))

    n_strips = len(adaptive_data)
    strip_height = 0.8
    if n_strips == 0:
        ax_strip.text(0.5, 0.5, "No adaptive solver sequence", ha="center", va="center")
        ax_strip.set_axis_off()
    else:
        for i, (t_ms_arr, numeric) in enumerate(adaptive_data):
            y_base = n_strips - 1 - i
            seg_start = 0
            for j in range(1, len(numeric) + 1):
                if j == len(numeric) or numeric[j] != numeric[seg_start]:
                    t_start = t_ms_arr[seg_start]
                    t_end = (
                        t_ms_arr[j]
                        if j < len(t_ms_arr)
                        else t_ms_arr[j - 1] + dt * 1e3
                    )
                    color = "#d62728" if numeric[seg_start] == 0 else "#2ecc71"
                    ax_strip.fill_between(
                        [t_start, t_end],
                        y_base,
                        y_base + strip_height,
                        color=color,
                        linewidth=0,
                        alpha=0.85,
                    )
                    seg_start = j

        ax_strip.set_yticks(
            [n_strips - 1 - i + strip_height / 2 for i in range(n_strips)]
        )
        ax_strip.set_yticklabels(adaptive_labels, fontsize=16, fontweight="bold")
        ax_strip.set_ylim(-0.1, n_strips)
        ax_strip.set_xlim(0, max_t_ms * 1.12 if max_t_ms > 0 else 1.0)
        ax_strip.set_xlabel("Time (ms)", fontsize=22, fontweight="bold")
        ax_strip.set_title("Solver Selection", fontsize=26, fontweight="bold", pad=40)
        ax_strip.tick_params(axis="x", labelsize=18, width=2.0, length=8)
        ax_strip.legend(
            handles=[
                Patch(facecolor="#d62728", edgecolor="black", label="CVODE"),
                Patch(facecolor="#2ecc71", edgecolor="black", label="QSS"),
            ],
            fontsize=14,
            framealpha=0.95,
            edgecolor="black",
            loc="lower left",
            bbox_to_anchor=(0.0, 1.02),
            ncol=2,
        )
        for spine in ax_strip.spines.values():
            spine.set_linewidth(3.0)
            spine.set_edgecolor("black")
        for i, (_, numeric) in enumerate(adaptive_data):
            cvode_pct = (numeric == 0).sum() / max(1, len(numeric)) * 100
            y_base = n_strips - 1 - i
            ax_strip.text(
                max_t_ms * 1.03,
                y_base + strip_height / 2,
                f"CVODE {cvode_pct:.0f}%",
                ha="left",
                va="center",
                fontsize=13,
                fontweight="bold",
                color="#d62728",
            )

    # ---- Bars: ignition delay + CPU ----
    inner_gs = GridSpecFromSubplotSpec(2, 1, subplot_spec=gs[2, 1], hspace=0.55)
    present = plot_order
    ign_delays = []
    cpu_means = []
    cpu_stds = []
    bar_colors = []
    for m in present:
        r = results[m]
        ign_delays.append(ignition_delay_s(r.trajectory, dt))
        mean, std = get_cpu_mean_std(results, m)
        cpu_means.append(mean)
        cpu_stds.append(std if np.isfinite(std) else 0.0)
        bar_colors.append(BAR_COLORS.get(m, "gray"))

    x = np.arange(len(present))
    short = [SHORT_LABELS.get(m, m) for m in present]

    ax_igd = fig.add_subplot(inner_gs[0])
    ax_igd.set_facecolor("white")
    vals_igd = [v * 1e3 if v is not None else 0.0 for v in ign_delays]
    ymax_igd = max(vals_igd) if vals_igd else 1.0
    bars = ax_igd.bar(
        x, vals_igd, width=0.6, color=bar_colors, edgecolor="black",
        linewidth=1.5, alpha=0.85,
    )
    for bar, val in zip(bars, vals_igd):
        ax_igd.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + ymax_igd * 0.02,
            f"{val:.2f}",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )
    ax_igd.set_xticks(x)
    ax_igd.set_xticklabels(short, fontsize=13, fontweight="bold")
    ax_igd.set_ylabel("Ign. Delay (ms)", fontsize=15, fontweight="bold")
    ax_igd.set_title("Ignition Delay", fontsize=18, fontweight="bold", pad=8)
    ax_igd.grid(True, axis="y", alpha=0.3)
    ax_igd.set_ylim(0, ymax_igd * 1.30 if ymax_igd > 0 else 1.0)
    for spine in ax_igd.spines.values():
        spine.set_linewidth(2.0)
        spine.set_edgecolor("black")

    ax_cpu = fig.add_subplot(inner_gs[1])
    ax_cpu.set_facecolor("white")
    y_max = max(
        (m + s for m, s in zip(cpu_means, cpu_stds) if np.isfinite(m)),
        default=1.0,
    )
    bars = ax_cpu.bar(
        x,
        cpu_means,
        width=0.6,
        color=bar_colors,
        edgecolor="black",
        linewidth=1.5,
        alpha=0.85,
        yerr=cpu_stds,
        capsize=4,
        error_kw={"elinewidth": 1.5},
    )
    for bar, mean, std in zip(bars, cpu_means, cpu_stds):
        label = (
            f"{mean:.2f}"
            if not np.isfinite(std) or std <= 0
            else f"{mean:.2f}±{std:.2f}"
        )
        ax_cpu.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + (std if np.isfinite(std) else 0) + y_max * 0.02,
            label,
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )
    ax_cpu.set_xticks(x)
    ax_cpu.set_xticklabels(short, fontsize=13, fontweight="bold")
    ax_cpu.set_ylabel("CPU Time (s)", fontsize=15, fontweight="bold")
    timing_n = results.get(TIMING_STATS_KEY, {}).get("CVODE", {}).get("n", 1)
    ax_cpu.set_title(
        f"CPU Time (mean ± std, n={timing_n})",
        fontsize=18,
        fontweight="bold",
        pad=8,
    )
    ax_cpu.grid(True, axis="y", alpha=0.3)
    ax_cpu.set_ylim(0, y_max * 1.35)
    for spine in ax_cpu.spines.values():
        spine.set_linewidth(2.0)
        spine.set_edgecolor("black")

    if title:
        fig.suptitle(title, fontsize=24, fontweight="bold", y=1.01)

    outdir.mkdir(parents=True, exist_ok=True)
    tag = f"{temp:.0f}K_{pressure_atm:.1f}atm"
    saved: List[Path] = []
    for ext in formats:
        out_path = outdir / f"0D_comparison_{tag}.{ext}"
        fig.savefig(
            out_path,
            dpi=dpi,
            bbox_inches="tight",
            facecolor="white",
            edgecolor="none",
        )
        saved.append(out_path)
    plt.close(fig)
    return saved

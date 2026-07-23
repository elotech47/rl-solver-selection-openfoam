#!/usr/bin/env python3
"""E17.2 QSS/RL campaign visualization vs pure CVODE.

Plots (per mode, and campaign compare):
  - Temperature contour
  - Solver selection RGB map: red=CVODE, green=QSS, yellow=CVODE-fallback
  - ΔT vs CVODE and chemCpuTime vs CVODE
  - CPU / usage timelines
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
from matplotlib.patches import Patch

N_CELLS_DEFAULT = 3200
NX, NY = 80, 40  # opposedJet_2D blockMesh


def parse_vol_scalar(path: Path, n_cells: int = N_CELLS_DEFAULT) -> np.ndarray | None:
    if not path.is_file():
        return None
    raw = path.read_bytes()
    # Detect format from FoamFile header
    head = raw[:800].decode("latin1", errors="ignore")
    is_binary = "format      binary" in head or "format\tbinary" in head

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

    # Binary: List<scalar>\nN\n( <N float64 LE> )
    m = re.search(rb"List<(?:scalar|label)>\s*\n\s*(\d+)\s*\n", raw)
    if not m:
        return None
    n = int(m.group(1))
    start = m.end()
    if raw[start : start + 1] == b"(":
        start += 1
    vals = np.frombuffer(raw[start : start + n * 8], dtype="<f8").copy()
    if len(vals) != n:
        return None
    return vals


def cell_xy(nx: int = NX, ny: int = NY) -> tuple[np.ndarray, np.ndarray]:
    # Match blockMesh opposed jet: x in [-0.01,0.01]? read from points if needed
    # Use mesh points for accurate extent
    return None, None  # filled below


def mesh_centres(mesh_dir: Path, nx: int = NX, ny: int = NY) -> tuple[np.ndarray, np.ndarray, list]:
    text = (mesh_dir / "points").read_text(errors="replace")
    coords = re.findall(r"\(([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\)", text)
    pts = np.array([(float(a), float(b)) for a, b, _ in coords], dtype=float)
    xs = np.unique(np.round(pts[:, 0], 12))
    ys = np.unique(np.round(pts[:, 1], 12))
    xc = 0.5 * (xs[:-1] + xs[1:])
    yc = 0.5 * (ys[:-1] + ys[1:])
    # OpenFOAM hex block: i varies fastest (x), then j (y)
    XX, YY = np.meshgrid(xc, yc, indexing="xy")
    # cell order: for j in ny for i in nx → ravel C on (ny,nx) with x fast
    x = np.tile(xc, ny)
    y = np.repeat(yc, nx)
    extent = [float(xs.min()), float(xs.max()), float(ys.min()), float(ys.max())]
    return x, y, extent


def to_grid(vals: np.ndarray, nx: int = NX, ny: int = NY) -> np.ndarray:
    if vals is None or len(vals) != nx * ny:
        raise ValueError(f"expected {nx*ny} cells, got {None if vals is None else len(vals)}")
    return vals.reshape((ny, nx), order="C")


def latest_time(fields: Path) -> str | None:
    times = []
    for p in fields.iterdir():
        if p.is_dir():
            try:
                times.append((float(p.name), p.name))
            except ValueError:
                continue
    return times[-1][1] if times else None


def nearest_time(fields: Path, target: float) -> str | None:
    best = None
    best_d = 1e9
    for p in fields.iterdir():
        if not p.is_dir():
            continue
        try:
            t = float(p.name)
        except ValueError:
            continue
        d = abs(t - target)
        if d < best_d:
            best_d = d
            best = p.name
    return best


def solver_rgb(flag: np.ndarray, fallback: np.ndarray) -> np.ndarray:
    """RGB image (ny,nx,3): red=CVODE, green=QSS, yellow=fallback CVODE."""
    g = to_grid(flag)
    fb = to_grid(fallback if fallback is not None else np.zeros_like(flag))
    rgb = np.zeros((*g.shape, 3), dtype=float)
    qss = g >= 0.5
    fell = (~qss) & (fb > 0.5)
    cvode = (~qss) & ~fell
    rgb[qss] = (0.15, 0.75, 0.25)       # green
    rgb[cvode] = (0.85, 0.12, 0.12)     # red
    rgb[fell] = (0.95, 0.85, 0.1)       # yellow
    return rgb


def imshow_field(ax, grid, extent, title, cmap="hot", vmin=None, vmax=None):
    im = ax.imshow(
        grid,
        origin="lower",
        extent=extent,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        aspect="equal",
        interpolation="nearest",
    )
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    return im


def load_usage(mode_dir: Path):
    p = mode_dir / "rl_usage_step.csv"
    if not p.is_file():
        return None
    with p.open() as f:
        return list(csv.DictReader(f))


def viz_mode(
    mode_dir: Path,
    cvode_fields: Path,
    out: Path,
    extent,
    time_name: str | None = None,
):
    fields = mode_dir / "fields"
    if not fields.is_dir():
        print(f"skip {mode_dir.name}: no fields")
        return
    tname = time_name or latest_time(fields)
    if not tname:
        print(f"skip {mode_dir.name}: no times")
        return
    tval = float(tname)
    T = parse_vol_scalar(fields / tname / "T")
    sf = parse_vol_scalar(fields / tname / "solverFlag")
    fb = parse_vol_scalar(fields / tname / "qssFallbackCount")
    cpu = parse_vol_scalar(fields / tname / "chemCpuTime")
    if T is None:
        print(f"skip {mode_dir.name}: no T at {tname}")
        return
    if sf is None:
        sf = np.ones(len(T))
    if fb is None:
        fb = np.zeros(len(T))

    cv_tname = nearest_time(cvode_fields, tval) if cvode_fields.is_dir() else None
    Tc = parse_vol_scalar(cvode_fields / cv_tname / "T") if cv_tname else None
    cpuc = parse_vol_scalar(cvode_fields / cv_tname / "chemCpuTime") if cv_tname else None

    # --- figure 1: T + solver RGB + fallback count ---
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 3.8))
    imshow_field(axes[0], to_grid(T), extent, f"{mode_dir.name}  T [K] @ t={tname}", "hot")
    axes[1].imshow(solver_rgb(sf, fb), origin="lower", extent=extent, aspect="equal", interpolation="nearest")
    axes[1].set_title(f"solver selection @ t={tname}", fontsize=10)
    axes[1].set_xlabel("x [m]")
    axes[1].set_ylabel("y [m]")
    axes[1].legend(
        handles=[
            Patch(facecolor=(0.85, 0.12, 0.12), label="CVODE"),
            Patch(facecolor=(0.15, 0.75, 0.25), label="QSS"),
            Patch(facecolor=(0.95, 0.85, 0.1), label="CVODE fallback"),
        ],
        loc="upper right",
        fontsize=8,
        framealpha=0.9,
    )
    imshow_field(
        axes[2],
        to_grid(fb),
        extent,
        f"qssFallbackCount @ t={tname}",
        "magma",
        vmin=0,
        vmax=max(1.0, float(fb.max())),
    )
    fig.suptitle(f"{mode_dir.name} — temperature & solver map", fontsize=12)
    fig.tight_layout()
    fig.savefig(out / f"{mode_dir.name}_T_solver.png", dpi=150)
    plt.close(fig)

    # --- figure 2: vs CVODE T and CPU ---
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 7.2))
    t_all = [T]
    if Tc is not None:
        t_all.append(Tc)
    vminT, vmaxT = float(min(a.min() for a in t_all)), float(max(a.max() for a in t_all))
    imshow_field(axes[0, 0], to_grid(T), extent, f"{mode_dir.name} T @ {tname}", "hot", vminT, vmaxT)
    if Tc is not None:
        imshow_field(axes[0, 1], to_grid(Tc), extent, f"CVODE T @ {cv_tname}", "hot", vminT, vmaxT)
        dT = T - Tc
        lim = max(abs(float(dT.min())), abs(float(dT.max())), 1.0)
        imshow_field(axes[0, 2], to_grid(dT), extent, f"ΔT ({mode_dir.name}−CVODE)", "coolwarm", -lim, lim)
    else:
        axes[0, 1].set_title("CVODE T missing")
        axes[0, 1].axis("off")
        axes[0, 2].axis("off")

    if cpu is not None:
        cpu_all = [cpu]
        if cpuc is not None:
            cpu_all.append(cpuc)
        vmaxC = float(max(a.max() for a in cpu_all))
        imshow_field(axes[1, 0], to_grid(cpu), extent, f"{mode_dir.name} chemCpuTime [s]", "viridis", 0, vmaxC)
        if cpuc is not None:
            imshow_field(axes[1, 1], to_grid(cpuc), extent, f"CVODE chemCpuTime @ {cv_tname}", "viridis", 0, vmaxC)
            ratio = np.divide(cpu, np.maximum(cpuc, 1e-12))
            imshow_field(
                axes[1, 2],
                to_grid(ratio),
                extent,
                f"CPU ratio ({mode_dir.name}/CVODE)",
                "plasma",
                0,
                float(np.percentile(ratio, 99)),
            )
        else:
            axes[1, 1].axis("off")
            axes[1, 2].axis("off")
        # annotate totals
        msg = f"Σcpu {mode_dir.name}={cpu.sum():.1f}s"
        if cpuc is not None:
            msg += f"  CVODE={cpuc.sum():.1f}s  ratio={cpu.sum()/max(cpuc.sum(),1e-12):.3f}"
        fig.text(0.5, 0.01, msg, ha="center", fontsize=9)
    else:
        for ax in axes[1]:
            ax.axis("off")

    fig.suptitle(f"{mode_dir.name} vs pure CVODE", fontsize=12)
    fig.tight_layout(rect=[0, 0.03, 1, 0.96])
    fig.savefig(out / f"{mode_dir.name}_vs_cvode.png", dpi=150)
    plt.close(fig)

    # --- usage timeline ---
    usage = load_usage(mode_dir)
    if usage:
        fig, axes = plt.subplots(2, 1, figsize=(8, 5.5), sharex=True)

        def col(*names):
            outv = []
            for r in usage:
                v = None
                for n in names:
                    if n in r and r[n] != "":
                        v = float(r[n])
                        break
                outv.append(np.nan if v is None else v)
            return np.array(outv)

        t = col("time", "t")
        axes[0].fill_between(t, 0, col("nQSS", "QSS"), color=(0.15, 0.75, 0.25), alpha=0.7, label="QSS")
        axes[0].fill_between(
            t, col("nQSS", "QSS"), col("nQSS", "QSS") + col("nFallbackCVODE", "fallbackCVODE", "nFallback"),
            color=(0.95, 0.85, 0.1), alpha=0.85, label="CVODE fallback",
        )
        axes[0].plot(t, col("nCVODE", "CVODE"), color=(0.85, 0.12, 0.12), lw=1.5, label="CVODE (policy)")
        axes[0].set_ylabel("cells")
        axes[0].legend(fontsize=8, loc="best")
        axes[0].set_title(f"{mode_dir.name} solver usage vs time")
        axes[1].plot(t, col("cpu_QSS"), color=(0.15, 0.75, 0.25), label="cpu_QSS")
        axes[1].plot(t, col("cpu_CVODE"), color=(0.85, 0.12, 0.12), label="cpu_CVODE")
        axes[1].plot(t, col("cpu_tot"), "k--", label="cpu_tot")
        axes[1].set_xlabel("t [s]")
        axes[1].set_ylabel("step chem CPU [s]")
        axes[1].legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out / f"{mode_dir.name}_usage_timeline.png", dpi=150)
        plt.close(fig)

    summary = {
        "mode": mode_dir.name,
        "time": tname,
        "Tmin": float(T.min()),
        "Tmax": float(T.max()),
        "nQSS": int((sf >= 0.5).sum()),
        "nCVODE": int(((sf < 0.5) & (fb < 0.5)).sum()),
        "nFallback": int((fb > 0.5).sum()),
        "fallback_max": float(fb.max()),
        "cpu_sum": float(cpu.sum()) if cpu is not None else None,
        "cvode_time": cv_tname,
        "cvode_Tmax": float(Tc.max()) if Tc is not None else None,
        "cvode_cpu_sum": float(cpuc.sum()) if cpuc is not None else None,
    }
    (out / f"{mode_dir.name}_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--modes", nargs="*", default=["qssOnly", "rlAdaptive"])
    ap.add_argument("--time", default=None, help="field time dir name (default: latest)")
    args = ap.parse_args()
    base = args.base
    out = base / "viz"
    out.mkdir(parents=True, exist_ok=True)

    mesh = Path(__file__).resolve().parents[3] / "cases/opposedJet_2D/constant/polyMesh"
    _, _, extent = mesh_centres(mesh)

    cvode_fields = base / "cvodeOnly" / "fields"
    if not cvode_fields.is_dir():
        alt = base.parent / "smoke_20260719_211924/cvodeOnly/fields"
        if alt.is_dir():
            cvode_fields = alt

    for name in args.modes:
        d = base / name
        if d.is_dir() and (d / "fields").is_dir():
            viz_mode(d, cvode_fields, out, extent, args.time)

    print(f"viz → {out}")


if __name__ == "__main__":
    main()

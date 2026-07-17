"""
Black-box evaluation runner.

Orchestrates:
  1. Load RL policy
  2. Build Cantera condition
  3. Run selected solvers via ``CompletePipeline``
  4. Optionally repeat for CPU mean ± std
  5. Persist results + write comparison plots + summary metrics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import cantera as ct
import numpy as np

from evaluation_pipeline import CompletePipeline
from inference import RLSolverSelector

from .config import ConditionSpec, EvalConfig, load_config
from .io_utils import (
    TIMING_STATS_KEY,
    condition_pkl_name,
    get_cpu_mean_std,
    save_json,
    save_results_pkl,
    write_summary_csv,
)
from .metrics import ignition_delay_s, range_normalized_temp_mse
from .plotting import plot_condition_comparison


@dataclass
class ConditionResult:
    """Per-condition outputs."""

    condition: ConditionSpec
    results: Dict[str, Any]
    pkl_path: Optional[Path] = None
    plot_paths: List[Path] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    """Aggregate output of a black-box evaluation run."""

    config: EvalConfig
    output_dir: Path
    conditions: List[ConditionResult] = field(default_factory=list)
    summary_csv: Optional[Path] = None
    config_snapshot: Optional[Path] = None


def _pipeline_condition(cfg: EvalConfig, cond: ConditionSpec) -> Dict[str, Any]:
    """Build the condition dict expected by ``CompletePipeline``."""
    pressure_pa = float(cond.pressure_atm) * ct.one_atm
    out: Dict[str, Any] = {
        "temp": float(cond.temp),
        "pressure": pressure_pa,
        "fuel": cfg.fuel,
        "oxidizer": cfg.oxidizer,
        "dt": float(cond.dt),
        "t_end": float(cond.t_end),
        "key_species": list(cfg.key_species),
    }
    if cond.phi is not None:
        out["phi"] = float(cond.phi)
    else:
        out["Z"] = float(cond.Z)
    return out


def _aggregate_cpu(samples: List[float]) -> Dict[str, Any]:
    arr = np.asarray(samples, dtype=float)
    n = len(arr)
    if n == 0:
        return {"mean": float("nan"), "std": float("nan"), "n": 0, "samples": []}
    std = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    return {
        "mean": float(np.mean(arr)),
        "std": std,
        "n": n,
        "samples": [float(x) for x in arr],
    }


def _is_result_key(key: str) -> bool:
    return key != TIMING_STATS_KEY and not str(key).startswith("__")


def _filter_methods(
    results: Dict[str, Any],
    methods: Sequence[str],
) -> Dict[str, Any]:
    """Keep only requested methods (+ timing block)."""
    out: Dict[str, Any] = {}
    for m in methods:
        if m in results:
            out[m] = results[m]
    if TIMING_STATS_KEY in results:
        timing = results[TIMING_STATS_KEY]
        out[TIMING_STATS_KEY] = {
            m: timing[m] for m in methods if m in timing
        }
    return out


def run_single_condition(
    cfg: EvalConfig,
    cond: ConditionSpec,
    rl_selector: RLSolverSelector,
) -> Dict[str, Any]:
    """
    Integrate one initial condition with all requested solvers.

    Timing: each method is executed ``cfg.n_repeats`` times. The first repeat
    records trajectories for plotting; subsequent repeats are timing-only.
    """
    condition = _pipeline_condition(cfg, cond)
    solver_cfg = cfg.solver_config_for_pipeline()

    want_supervised = (
        "Supervised-ML" in cfg.methods and cfg.supervised_model_dir is not None
    )
    # Pipeline always can run CVODE/QSS/RL; Supervised-ML needs a model dir.
    # We run all available solvers then filter to ``cfg.methods``.
    only_methods = None
    # If user only wants RL (unusual), still need baselines if listed.
    # CompletePipeline.run_all_solvers supports only_methods for subset runs.

    cpu_samples: Dict[str, List[float]] = {}
    plot_run: Optional[Dict[str, Any]] = None

    for rep in range(cfg.n_repeats):
        record_traj = bool(cfg.record_trajectory and rep == 0)
        rl_selector.reset()

        pipeline = CompletePipeline(
            mechanism=str(cfg.mechanism_path),
            condition=condition,
            config=dict(solver_cfg),
            rl_selector=rl_selector,
            supervised_model_dir=(
                str(cfg.supervised_model_dir) if want_supervised else None
            ),
            supervised_error_threshold=cfg.supervised_error_threshold,
            supervised_device=cfg.device,
            confidence_threshold=cfg.confidence_threshold,
            heuristic_fns=None,
        )
        pipeline.evaluator.config.record_trajectory = record_traj

        rep_results = pipeline.run_all_solvers(
            generate_reference=False,
            only_methods=only_methods,
        )

        for name, result in rep_results.items():
            if not _is_result_key(name):
                continue
            cpu_samples.setdefault(name, []).append(float(result.cpu_time))

        if plot_run is None:
            plot_run = {
                k: v for k, v in rep_results.items() if _is_result_key(k)
            }

        print(
            f"    Repeat {rep + 1}/{cfg.n_repeats} done"
            + (" (trajectories recorded)" if record_traj else " (timing only)")
        )

    assert plot_run is not None
    timing_stats = {
        name: _aggregate_cpu(samples) for name, samples in cpu_samples.items()
    }
    out = dict(plot_run)
    out[TIMING_STATS_KEY] = timing_stats
    return _filter_methods(out, cfg.methods)


def _condition_metrics(
    results: Dict[str, Any],
    cond: ConditionSpec,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "condition": cond.display_label(),
        "temp_K": cond.temp,
        "pressure_atm": cond.pressure_atm,
        "Z": cond.Z if cond.phi is None else None,
        "phi": cond.phi,
        "dt": cond.dt,
        "t_end": cond.t_end,
    }

    ref = results.get("CVODE")
    ref_traj = (
        ref.trajectory
        if ref is not None and getattr(ref, "trajectory", None) is not None
        else None
    )

    for method in ("CVODE", "QSS", "RL-Adaptive", "Supervised-ML"):
        r = results.get(method)
        if r is None or getattr(r, "trajectory", None) is None:
            continue
        key = method.replace("-", "_").replace(" ", "_")
        ign = ignition_delay_s(r.trajectory, cond.dt)
        mean_cpu, std_cpu = get_cpu_mean_std(results, method)
        row[f"{key}_ignition_delay_ms"] = (
            ign * 1e3 if ign is not None else float("nan")
        )
        row[f"{key}_cpu_mean_s"] = mean_cpu
        row[f"{key}_cpu_std_s"] = std_cpu
        if ref_traj is not None and method != "CVODE":
            mse, rmse = range_normalized_temp_mse(r.trajectory, ref_traj)
            row[f"{key}_norm_temp_mse_vs_cvode"] = mse
            row[f"{key}_norm_temp_rmse_vs_cvode"] = rmse

    cvode_cpu = row.get("CVODE_cpu_mean_s")
    rl_cpu = row.get("RL_Adaptive_cpu_mean_s")
    if (
        cvode_cpu is not None
        and rl_cpu is not None
        and np.isfinite(cvode_cpu)
        and np.isfinite(rl_cpu)
        and rl_cpu > 0
    ):
        row["speedup_cvode_over_rl"] = float(cvode_cpu) / float(rl_cpu)

    cvode_ign = row.get("CVODE_ignition_delay_ms")
    rl_ign = row.get("RL_Adaptive_ignition_delay_ms")
    if (
        cvode_ign is not None
        and rl_ign is not None
        and np.isfinite(cvode_ign)
        and np.isfinite(rl_ign)
        and cvode_ign > 0
    ):
        row["rl_ignition_delay_error_pct"] = (
            abs(float(rl_ign) - float(cvode_ign)) / float(cvode_ign) * 100.0
        )

    return row


def _print_banner(cfg: EvalConfig) -> None:
    print("=" * 72)
    print(" Adaptive Chemistry Solver Selection — Black-Box Evaluation")
    print("=" * 72)
    print(f"  Mechanism : {cfg.mechanism}")
    print(f"             {cfg.mechanism_path}")
    print(f"  Model     : {cfg.model_path}")
    print(f"  Device    : {cfg.device}")
    print(
        f"  Policy    : use_prev_state={cfg.use_prev_state}, "
        f"use_gradient_only={cfg.use_gradient_only}, "
        f"num_steps={cfg.num_steps}, "
        f"confidence={cfg.confidence_threshold}"
    )
    print(f"  Network   : {cfg.network}")
    print(f"  Methods   : {cfg.methods}")
    print(f"  Conditions: {len(cfg.conditions)}")
    print(f"  Repeats   : {cfg.n_repeats}")
    if cfg.supervised_model_dir:
        print(f"  Sup-ML    : {cfg.supervised_model_dir}")
        print(f"             threshold={cfg.supervised_error_threshold:g}")
    print(f"  Output    : {cfg.output_dir}")
    print("=" * 72)


def run(cfg: EvalConfig) -> RunResult:
    """
    Execute a fully resolved evaluation configuration.

    This is the primary library entry point. Prefer :func:`run_from_config`
    when starting from a YAML file.
    """
    _print_banner(cfg)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    # Snapshot resolved config for provenance.
    snapshot_path = cfg.output_dir / "resolved_config.json"
    save_json(
        {
            "mechanism": cfg.mechanism,
            "mechanism_path": str(cfg.mechanism_path),
            "fuel": cfg.fuel,
            "oxidizer": cfg.oxidizer,
            "key_species": cfg.key_species,
            "model_path": str(cfg.model_path),
            "network": cfg.network,
            "use_prev_state": cfg.use_prev_state,
            "use_gradient_only": cfg.use_gradient_only,
            "confidence_threshold": cfg.confidence_threshold,
            "num_steps": cfg.num_steps,
            "methods": cfg.methods,
            "device": cfg.device,
            "n_repeats": cfg.n_repeats,
            "supervised_model_dir": (
                str(cfg.supervised_model_dir)
                if cfg.supervised_model_dir
                else None
            ),
            "supervised_error_threshold": cfg.supervised_error_threshold,
            "solver": cfg.solver,
            "output_dir": str(cfg.output_dir),
            "conditions": [
                {
                    "label": c.display_label(),
                    "temp": c.temp,
                    "pressure_atm": c.pressure_atm,
                    "Z": c.Z,
                    "phi": c.phi,
                    "dt": c.dt,
                    "t_end": c.t_end,
                }
                for c in cfg.conditions
            ],
            "raw_yaml": cfg.raw,
        },
        snapshot_path,
    )

    print("\nLoading RL policy…")
    rl_selector = RLSolverSelector(
        model_path=str(cfg.model_path),
        mechanism_file=str(cfg.mechanism_path),
        device=cfg.device,
        network_config=dict(cfg.network),
        key_species=list(cfg.key_species),
        use_prev_state=cfg.use_prev_state,
        confidence_threshold=cfg.confidence_threshold,
        use_gradient_only=cfg.use_gradient_only,
    )

    gas = ct.Solution(str(cfg.mechanism_path))
    aggregate = RunResult(
        config=cfg,
        output_dir=cfg.output_dir,
        config_snapshot=snapshot_path,
    )
    summary_rows: List[Dict[str, Any]] = []

    for i, cond in enumerate(cfg.conditions):
        label = cond.display_label()
        print(f"\n{'─' * 72}")
        print(f" Condition {i + 1}/{len(cfg.conditions)}: {label}")
        print(f"{'─' * 72}")

        results = run_single_condition(cfg, cond, rl_selector)
        metrics = _condition_metrics(results, cond)
        summary_rows.append(metrics)

        # Console metrics
        for k, v in metrics.items():
            if k == "condition":
                continue
            if isinstance(v, float):
                print(f"  {k}: {v:.6g}")
            elif v is not None:
                print(f"  {k}: {v}")

        pkl_path = None
        if cfg.save_pkl:
            pkl_path = cfg.output_dir / condition_pkl_name(
                cond.temp, cond.pressure_atm, cond.Z if cond.phi is None else cond.phi or 0.0
            )
            # Prefer Z in filename when available.
            if cond.phi is None:
                pkl_path = cfg.output_dir / condition_pkl_name(
                    cond.temp, cond.pressure_atm, cond.Z
                )
            save_results_pkl(results, pkl_path)
            print(f"  Saved pkl → {pkl_path}")

        plot_paths: List[Path] = []
        if cfg.plot.enable:
            compare = cfg.plot.compare_methods or cfg.methods
            plot_paths = plot_condition_comparison(
                results,
                temp=cond.temp,
                pressure_atm=cond.pressure_atm,
                dt=cond.dt,
                outdir=cfg.output_dir,
                gas=gas,
                species_to_plot=cfg.plot.species,
                methods=compare,
                title=label,
                formats=cfg.plot.formats,
                dpi=cfg.plot.dpi,
            )
            for p in plot_paths:
                print(f"  Saved plot → {p}")

        aggregate.conditions.append(
            ConditionResult(
                condition=cond,
                results=results,
                pkl_path=pkl_path,
                plot_paths=plot_paths,
                metrics=metrics,
            )
        )

    if cfg.save_summary_csv and summary_rows:
        csv_path = cfg.output_dir / "summary.csv"
        write_summary_csv(summary_rows, csv_path)
        aggregate.summary_csv = csv_path
        print(f"\nSummary CSV → {csv_path}")

    print("\nDone.")
    return aggregate


def run_from_config(
    config_path: str | Path,
    *,
    overrides: Optional[Sequence[str]] = None,
    repo_root: Optional[Path] = None,
) -> RunResult:
    """
    Load a YAML config and execute the evaluation.

    Parameters
    ----------
    config_path:
        Path to the YAML configuration file.
    overrides:
        Optional ``key.subkey=value`` overrides (same syntax as CLI ``--set``).
    repo_root:
        Repository root for resolving relative paths. Defaults to the
        solver_selection project root.
    """
    cfg = load_config(config_path, overrides=overrides, repo_root=repo_root)
    return run(cfg)

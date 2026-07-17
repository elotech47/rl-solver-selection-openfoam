# Architecture

This document explains how the handoff black box relates to the research codebase, for maintainers and reviewers who need to audit or extend it.

---

## Design goals

1. **Single config surface** — one YAML file describes mechanism, policy, observation mode, baselines, integrator tolerances, and plotting.
2. **No training code in the path** — evaluation only; no PPO updates, no environment rollouts for learning.
3. **Stable, professional API** — `run_from_config` / `run` / CLI; detailed docs for collaborators.
4. **Thin wrapper** — reuse `CompletePipeline` and `RLSolverSelector` rather than re-implementing integrators.

---

## Data flow

```
┌─────────────────────┐
│  YAML config file   │
│  (+ CLI --set)      │
└──────────┬──────────┘
           │ load_config()
           ▼
┌─────────────────────┐
│     EvalConfig      │  validated dataclass
└──────────┬──────────┘
           │ run()
           ▼
┌─────────────────────┐     checkpoint.pt
│  RLSolverSelector   │◄──────────────────
└──────────┬──────────┘
           │ per condition
           ▼
┌─────────────────────┐
│  CompletePipeline   │──► CVODE / QSS / RL-Adaptive [/ Supervised-ML]
└──────────┬──────────┘
           │
           ├─► pickle (trajectories, solver_sequence, CPU)
           ├─► summary.csv (IDT, MSE, speedup)
           ├─► resolved_config.json
           └─► 0D_comparison_*.png/pdf
```

---

## Module responsibilities

| Module | Responsibility | Depends on research code? |
|--------|----------------|---------------------------|
| `config.py` | Parse YAML, path resolution, validation, `--set` | `utils.MECHANISM_CONFIGS` |
| `runner.py` | Orchestrate repeats, filter methods, metrics, I/O | `CompletePipeline`, `RLSolverSelector`, Cantera |
| `plotting.py` | Comparison figures | Matplotlib, Cantera (species index) |
| `metrics.py` | Ignition delay, range-normalized temp MSE | NumPy only |
| `io_utils.py` | Pickle / CSV / JSON | stdlib |
| `cli.py` | Argparse entry | — |

---

## Observation construction (important)

There are **two** places observation flags can live:

1. `RLSolverSelector(use_prev_state=..., use_gradient_only=...)` — used by direct `select_solver(T,Y,P)` APIs (e.g. CFD wrappers).
2. `CompletePipeline` / `ObservationBuilder` via the **solver config** dict — used by 0-D adaptive RL evaluation.

The handoff sets **both** from `policy.use_prev_state` / `policy.use_gradient_only` so they cannot diverge.

Typical dimensions with 8 key species:

| Mode | Approx. dim |
|------|-------------|
| State only | 10 |
| State + gradients (`use_prev_state`) | 19 |
| Gradients only (`use_gradient_only`) | 10 |

Checkpoint `feature_extractor.0.weight` shape `[hidden0, obs_dim]` must match.

Normalization: if the checkpoint stores `obs_rms`, `RLSolverSelector` restores it so inference uses the same running mean/variance as training.

---

## How methods are selected at runtime

Inside `AdaptiveRLStrategy` (in `evaluation_pipeline.py`):

1. Integrate `num_steps` micro-steps with the last chosen solver (or after a fresh policy query).
2. Build an observation from the current state.
3. Call `rl_selector._select_action(obs)` → discrete action `{0: CVODE, 1: QSS}` + confidence.
4. If confidence `< confidence_threshold`, force CVODE.
5. On integrator failure, fall back to the other solver and record labels such as `CVODE->QSS`.

Supervised-ML uses a separate strategy: neural nets predict CPU and error for each integrator; among candidates under `error_threshold`, pick the fastest, else the lowest error.

---

## Timing repeats

```
for rep in 1 .. n_repeats:
    rl_selector.reset()
    run_all_solvers(record_trajectory = (rep == 1))
    collect cpu_time samples
```

Results dictionary:

```python
{
  "CVODE": ProfilingResult(...),
  "QSS": ProfilingResult(...),
  "RL-Adaptive": ProfilingResult(...),
  "Supervised-ML": ProfilingResult(...),   # optional
  "__cpu_timing__": {
      "CVODE": {"mean": ..., "std": ..., "n": ..., "samples": [...]},
      ...
  }
}
```

Only methods listed in `config.methods` are retained after the run.

---

## Metrics definitions

### Ignition delay

\[
t_{\mathrm{ign}} = i^{*} \Delta t, \qquad i^{*} = \arg\max_i \frac{T_{i+1}-T_i}{\Delta t}
\]

### Range-normalized temperature MSE (vs CVODE)

Using the reference (CVODE) temperature range over the whole trajectory:

\[
\hat T = \frac{T - T_{\mathrm{ref,min}}}{T_{\mathrm{ref,max}} - T_{\mathrm{ref,min}} + \epsilon},
\quad
\mathrm{MSE} = \mathrm{mean}\bigl((\hat T_{\mathrm{method}} - \hat T_{\mathrm{ref}})^{2}\bigr)
\]

This matches the “normalize by ref min/max, then MSE” definition requested for paper analysis and is implemented in `metrics.range_normalized_temp_mse`.

### Speedup

\[
S = \frac{\overline{\mathrm{CPU}}_{\mathrm{CVODE}}}{\overline{\mathrm{CPU}}_{\mathrm{RL}}}
\]

---

## Extending the handoff

### Add a new named mechanism

1. Add an entry to `utils.MECHANISM_CONFIGS`.
2. Place the Cantera YAML under the path you declare.
3. Use `mechanism: your_key` in the YAML.

### Change plotting style

Edit `handoff/blackbox/plotting.py`. Keep the public function `plot_condition_comparison(...)` so `runner.py` stays stable.

### Plot-only mode from existing pickles

Not built into v1 of the handoff CLI. You can:

```python
from handoff.blackbox.io_utils import load_results_pkl
from handoff.blackbox.plotting import plot_condition_comparison
import cantera as ct

results = load_results_pkl("handoff_runs/demo/condition_800K_10.0atm_0.062.pkl")
gas = ct.Solution("large_mechanism/n-dodecane.yaml")
plot_condition_comparison(
    results, temp=800, pressure_atm=10.0, dt=1e-6,
    outdir=Path("handoff_runs/demo"), gas=gas,
    species_to_plot=["OH", "CO2", "H2O"],
)
```

### Wire a different checkpoint series

Duplicate an example YAML, change `policy.model_path` and observation flags, and point `output.dir` to a fresh folder. Do not mix observation settings across checkpoints.

---

## Non-goals (out of scope for this package)

- Online training / PPO updates
- HPC SLURM sweeps (`run_sweep.py`, retro-eval workers)
- Multi-policy batch ablations (`multi_policy_eval.py`)
- CFD coupling (use `RLSolverSelector.select_solver` / batch APIs directly)

Those remain in the parent research codebase; this handoff is intentionally **evaluation-only** and **config-driven**.

# Adaptive Chemistry Solver Selection — Evaluation Handoff

**Audience.** Collaborators and reviewers who need to **evaluate a trained RL policy** on 0-D homogeneous reactors **without** reading the training stack.

**What this package does.** Given:

1. an **initial condition** (temperature, pressure, mixture fraction or \(\phi\)),
2. a **mechanism** (Cantera YAML or named key),
3. a **trained policy** (`.pt` checkpoint),
4. a **YAML config** (observation flags, integrator tolerances, which baselines to run, plotting),

it:

- integrates the reactor with **CVODE**, **QSS**, **RL-Adaptive**, and optionally **Supervised-ML**,
- saves trajectories (pickle), a metrics summary (CSV), and a provenance snapshot (JSON),
- writes **comparison plots** (temperature, species, solver-selection strips, ignition-delay & CPU bars).

You should not need to call `CompletePipeline` or `RLSolverSelector` yourself—the black box wraps them.

---

## Quick start

```bash
# From the solver_selection repository root
workon rlenv          # or: source /path/to/your/venv/bin/activate

# Point the example config at your checkpoint, then run:
python handoff/run.py --config handoff/configs/example_ndodecane.yaml \
    --set policy.model_path=/absolute/or/relative/path/to/policy.pt \
    --set output.dir=handoff_runs/demo
```

Equivalent module form:

```bash
python -m handoff.blackbox --config handoff/configs/example_ndodecane.yaml
```

Python API:

```python
from handoff.blackbox import run_from_config

result = run_from_config(
    "handoff/configs/example_minimal.yaml",
    overrides=["policy.model_path=my_policy.pt", "output.dir=handoff_runs/api_demo"],
)
print(result.output_dir)
print(result.summary_csv)
```

---

## Repository layout (handoff only)

```
handoff/
├── README.md                          ← this file
├── run.py                             ← CLI launcher
├── configs/
│   ├── example_ndodecane.yaml         ← 4 paper-style conditions
│   ├── example_minimal.yaml           ← single condition
│   └── example_with_supervised.yaml   ← includes Sup-ML baseline
├── docs/
│   ├── CONFIG_REFERENCE.md            ← every YAML field explained
│   └── ARCHITECTURE.md                ← how the black box maps to the core codes
└── blackbox/
    ├── __init__.py                    ← public API
    ├── __main__.py                    ← python -m handoff.blackbox
    ├── cli.py                         ← argparse
    ├── config.py                      ← load / validate / --set overrides
    ├── runner.py                      ← orchestration
    ├── plotting.py                    ← comparison figures
    ├── metrics.py                     ← ignition delay, norm. temp MSE
    └── io_utils.py                    ← pickle / CSV / JSON helpers
```

Core science code that this wraps (already in the parent repo):

| Module | Role |
|--------|------|
| `inference.RLSolverSelector` | Load PPO checkpoint, select CVODE vs QSS |
| `evaluation_pipeline.CompletePipeline` | Run CVODE / QSS / RL / Supervised-ML |
| `utils.MECHANISM_CONFIGS` | Named mechanisms → fuel / oxidizer / path |
| `solver_strategy` | CVODE / QSS integrators |

---

## What you must get right (critical)

### 1. Observation flags must match training

The policy’s observation vector is built inside `CompletePipeline` from config flags. A mismatch yields garbage actions or a shape error when loading weights.

| Training setting | Config to set |
|------------------|---------------|
| State + temporal derivatives | `policy.use_prev_state: true`, `policy.use_gradient_only: false` |
| Gradients only | `policy.use_gradient_only: true` (set `use_prev_state: false`) |
| Decision every \(N\) micro-steps | `policy.num_steps: N` (often `20`) |
| MLP widths / activation | `policy.network.hidden_dims`, `policy.network.activation` |

These values are usually those used in the training YAML (`configs/default.yaml` → `environment` and `network` sections).

### 2. Mechanism and key species must match training

Use the same Cantera mechanism and the same ordered `key_species` list the policy saw during training. Named keys (`ndodecane`, `methane`, `hydrogen`, `jetA`) pull defaults from `utils.MECHANISM_CONFIGS`.

### 3. Checkpoint path

`policy.model_path` must point to a `.pt` file that contains either a full training checkpoint (`network_state_dict`, preferably with `obs_rms`) or a raw `state_dict` with the same layer names.

---

## Config overview

A complete annotated example lives at [`configs/example_ndodecane.yaml`](configs/example_ndodecane.yaml). Field-by-field documentation: [`docs/CONFIG_REFERENCE.md`](docs/CONFIG_REFERENCE.md).

Minimal structure:

```yaml
mechanism: ndodecane          # or path/to/mech.yaml + fuel/oxidizer

policy:
  model_path: path/to/policy.pt
  use_prev_state: true
  use_gradient_only: false
  num_steps: 20
  network:
    hidden_dims: [256, 128, 64]
    activation: relu

methods: [CVODE, QSS, RL-Adaptive]

conditions:
  - temp: 800
    pressure_atm: 10.0
    Z: 0.062
    dt: 1.0e-6
    t_end: 3.5e-3

output:
  dir: handoff_runs/my_run
  plot:
    enable: true
```

### CLI overrides

Any nested field can be overridden without editing YAML:

```bash
python handoff/run.py --config handoff/configs/example_minimal.yaml \
  --set device=cpu \
  --set policy.use_gradient_only=true \
  --set policy.use_prev_state=false \
  --set n_repeats=5 \
  --set output.plot.enable=false
```

Booleans: `true`/`false`. Lists: `[CVODE,QSS,RL-Adaptive]`.

> **zsh note:** quote list overrides so the shell does not expand brackets:
> `--set "output.plot.formats=[png]"`.

---

## Outputs

For `output.dir = handoff_runs/demo`, a successful run writes:

| Artifact | Description |
|----------|-------------|
| `resolved_config.json` | Snapshot of the fully resolved settings (provenance) |
| `condition_{T}K_{P}atm_{Z}.pkl` | Dict of method → `ProfilingResult` (+ `__cpu_timing__`) |
| `summary.csv` | Per-condition ignition delays, CPU, speedup, norm. temp MSE |
| `0D_comparison_{T}K_{P}atm.png/.pdf` | Comparison figure (if plotting enabled) |

### Metrics reported in `summary.csv`

- **Ignition delay** — time of \(\max dT/dt\) (same definition as the paper scripts).
- **CPU time** — mean ± std over `n_repeats`.
- **Speedup** — \(\mathrm{CPU_{CVODE}} / \mathrm{CPU_{RL}}\).
- **Ignition-delay error %** — \(|t_{\mathrm{RL}} - t_{\mathrm{CVODE}}| / t_{\mathrm{CVODE}} \times 100\).
- **Range-normalized temperature MSE** — temperatures scaled by CVODE \([T_{\min}, T_{\max}]\), then MSE (see `metrics.py`).

---

## Methods

| Method key | Role |
|------------|------|
| `CVODE` | Accurate stiff ODE baseline (reference trajectory) |
| `QSS` | Fast quasi-steady-state approximate integrator |
| `RL-Adaptive` | Trained policy choosing CVODE vs QSS each decision block |
| `Supervised-ML` | Optional classifier baseline; requires `supervised.model_dir` |

To plot only a subset of what you ran:

```yaml
methods: [CVODE, QSS, RL-Adaptive, Supervised-ML]
output:
  plot:
    compare_methods: [CVODE, QSS, RL-Adaptive]   # omit Sup-ML from the figure
```

---

## Environment / dependencies

Same stack as the rest of this repository (virtualenv **rlenv** recommended):

- Python 3.9+
- NumPy, PyYAML, Matplotlib
- PyTorch
- Cantera
- Project-local packages (`qss_integrator`, Sundials bindings, etc.) already required by `evaluation_pipeline`

Activate your env, then run from the **repository root** so imports (`inference`, `evaluation_pipeline`, `utils`) resolve.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| `size mismatch` loading network | Wrong `network.hidden_dims` / `activation`, or obs dim ≠ training (`use_prev_state` / `use_gradient_only`) |
| Policy always picks QSS | Missing `obs_rms` in checkpoint, or observation flags wrong |
| `Supervised-ML` rejected by config | Listed in `methods` but `supervised.model_dir` unset |
| Mechanism file not found | Use named key (`ndodecane`) or absolute path; run from repo root |
| Plots missing a species | Species not in mechanism (e.g. `CO2` absent); edit `output.plot.species` |

---

## Further reading

- [`docs/CONFIG_REFERENCE.md`](docs/CONFIG_REFERENCE.md) — exhaustive YAML schema
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — data flow and how this maps onto the research code
- Parent repo [`CLAUDE.md`](../CLAUDE.md) / [`README.md`](../README.md) — training and HPC evaluation

---

## License / citation

Use according to the parent project’s license. If you publish results produced with this handoff, please cite the accompanying paper and acknowledge the mechanism sources.

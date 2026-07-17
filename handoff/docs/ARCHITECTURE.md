# Architecture (self-contained package)

## Design intent

The handoff must be **installable and free of imports from the parent research
repository**. All Python modules required to evaluate a policy are **vendored**
under `src/solver_selection_handoff/` and installed as a single distribution
(`solver-selection-handoff`).

```
                    pip install -e handoff/
                              │
                              ▼
              import solver_selection_handoff
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
     blackbox/           vendored cores      data/mechanisms/
   (config, CLI,         inference           n-dodecane.yaml
    runner, plots)       evaluation_pipeline ch4_53species.yaml
                         solver_strategy     mech.yaml
                         ppo_agent
                         utils
                         train_supervised_nets
```

## Import graph (closed)

```
blackbox.runner
    → evaluation_pipeline.CompletePipeline
        → solver_strategy  → utils.create_solver
        → inference.RLSolverSelector → ppo_agent
        → train_supervised_nets.MLP   (Supervised-ML only)

blackbox.config
    → utils.MECHANISM_CONFIGS / resolve_mechanism_path
```

No references to paths like `../inference.py` or `sys.path` hacks into a parent
repo after installation.

## Mechanism resolution

Named keys (`ndodecane`, `methane`, `jetA`) resolve to files under

```
solver_selection_handoff/data/mechanisms/
```

shipped via `package-data` in `pyproject.toml`.

`hydrogen` uses Cantera’s built-in `h2o2.yaml` (not shipped).

Custom mechanisms: set `mechanism: /abs/path/mech.yaml` plus `fuel` / `oxidizer`.

## External (pip) dependencies that cannot be vendored as pure Python

| Package | Why |
|---------|-----|
| `torch` | Neural nets |
| `cantera` | Chemistry |
| `SundialsPy` | Compiled CVODE bindings |
| `qss-integrator` | Compiled QSS extension |
| `scipy` | Scipy-BDF CVODE path used inside adaptive strategies |
| `numpy`, `matplotlib`, `seaborn`, `tqdm`, `PyYAML` | Numerics / I/O / UX |

These must be available in the install environment. Document versions used in
your lab’s research env when shipping to collaborators if exact reproducibility
of timing matters.

## Console entry point

`pyproject.toml`:

```toml
[project.scripts]
solver-selection-eval = "solver_selection_handoff.blackbox.cli:main"
```

## Relating to the original research repo

The vendored `.py` files are **snapshots** of the research modules at packaging
time. Bug fixes that land only in the parent repo must be **re-copied** here
(or cherry-picked) when you cut a new handoff release. This isolation is
intentional: a recipient should not need the parent tree.

## Evaluation data flow

Same as before:

1. Load YAML → `EvalConfig`
2. `RLSolverSelector(checkpoint, mechanism, network, flags)`
3. Per condition: `CompletePipeline.run_all_solvers` (± timing repeats)
4. Filter to configured `methods`
5. Persist pickle / CSV / plots

Metrics (ignition delay, range-normalised temperature MSE) are defined in
`blackbox/metrics.py` and summarised in `summary.csv`.

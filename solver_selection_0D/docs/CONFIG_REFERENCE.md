# Configuration reference

Every field accepted by the black-box YAML config is documented below.
Unset optional fields fall back to the defaults listed in each subsection.

Paths that are not absolute are resolved relative to:

1. the **config file’s directory** (for `policy.model_path` / `supervised.model_dir` when that helps), then
2. the **repository root** (`solver_selection/`).

Named mechanisms are always resolved from the repository root via `utils.MECHANISM_CONFIGS`.

---

## Top-level fields

### `mechanism` *(required)*

**Type:** string  
**Meaning:** Either:

- a **named key**: `hydrogen` | `methane` | `ndodecane` | `jetA`, or
- a **filesystem path** to a Cantera mechanism YAML.

When using a named key, `fuel`, `oxidizer`, and `key_species` default to the table in `utils.MECHANISM_CONFIGS`.

When using a path, you **must** also set `fuel` and `oxidizer`.

```yaml
mechanism: ndodecane
# or
mechanism: large_mechanism/n-dodecane.yaml
fuel: "nc12h26:1.0"
oxidizer: "n2:3.76, o2:1.0"
```

### `fuel` / `oxidizer` *(optional if named mechanism)*

**Type:** string (Cantera composition)  
Examples: `"nc12h26:1.0"`, `"n2:3.76, o2:1.0"`.

### `key_species` *(optional)*

**Type:** list of strings  
**Default (named mechs):** from `MECHANISM_CONFIGS`  
**Default (path):** `[OH, H2O, O2, H2, H2O2, O, H, N2]`

Species used to build the RL observation. **Order matters** and must match training. All species must exist in the mechanism.

### `device` *(optional)*

**Type:** string  
**Default:** `cpu`  
**Values:** `cpu` | `cuda` (or any valid PyTorch device string)

### `n_repeats` *(optional)*

**Type:** integer ≥ 1  
**Default:** `1`  

Number of timed integrations per method per condition. Repeat 1 records trajectories for plots; later repeats are timing-only and contribute to CPU mean ± std.

### `record_trajectory` *(optional)*

**Type:** bool  
**Default:** `true`  
If `false`, trajectories are not stored (plots/metrics that need \(T(t)\) will be limited).

### `methods` *(optional)*

**Type:** list of strings  
**Default:** `[CVODE, QSS, RL-Adaptive]`  
**Allowed:** `CVODE`, `QSS`, `RL-Adaptive`, `Supervised-ML`

Notes:

- Must include `RL-Adaptive`.
- `Supervised-ML` requires the `supervised:` block.
- Methods not listed are discarded from saved results and plots even if the pipeline could run them.

---

## `policy` block *(required)*

### `policy.model_path` *(required)*

**Type:** string (path to `.pt`)

### `policy.use_prev_state` *(optional)*

**Type:** bool  
**Default:** `true`  

Append temporal derivatives \([dT/dt,\,dY_i/dt,\ldots]\) to the observation when `use_gradient_only` is false.

### `policy.use_gradient_only` *(optional)*

**Type:** bool  
**Default:** `false`  

If `true`, the observation is **only** \([dT/dt,\,dY_i/dt,\ldots,\,P_{\mathrm{norm}}]\) (typical dim 10 for 8 key species). Must match policies trained with `environment.use_gradient_only: true`.

### `policy.num_steps` *(optional)*

**Type:** int  
**Default:** `20`  

Number of micro-integrations between RL queries. Training configs often use `20`. Paper scripts sometimes used `50`—**use the training value**.

### `policy.confidence_threshold` *(optional)*

**Type:** float  
**Default:** `0.6`  

If the policy’s softmax confidence is below this value, the adaptive runner forces **CVODE** for that decision block.

### `policy.network` *(optional)*

```yaml
network:
  hidden_dims: [256, 128, 64]   # list[int]
  activation: relu              # relu | tanh
```

**Defaults:** `[256, 128, 64]` / `relu` (current trained n-dodecane policies).  
`inference.RLSolverSelector` itself defaults to `[256,256,128]/tanh` if you call it outside this handoff—**do not rely on that**; always set `network` explicitly in the YAML.

---

## `supervised` block *(optional)*

Required only when `Supervised-ML` is listed under `methods`.

```yaml
supervised:
  model_dir: path/to/dir
  error_threshold: 1.0e-4
```

### Expected directory contents

```
model_dir/
  meta.json
  normalizer.npz
  cpu_net.pt
  err_net.pt
```

`error_threshold` is the maximum predicted relative error allowed when selecting an integrator (see `evaluation_pipeline` / supervised training docs).

---

## `solver` block *(optional)*

Integrator tolerances forwarded into `CompletePipeline` / `solver_strategy`. Defaults:

| Key | Default | Notes |
|-----|---------|-------|
| `cvode_rtol` | `1e-8` | Relative tolerance |
| `cvode_atol` | `1e-12` | Absolute tolerance |
| `qss_dtmin` | `1e-12` | QSS min step |
| `qss_dtmax` | `1e-6` | QSS max step |
| `qss_abstol` | `1e-11` | QSS absolute tolerance |
| `qss_itermax` | `2` | QSS corrector iterations |
| `epsmin` / `epsmax` | `0.02` / `100` | QSS step controllers |
| `mxsteps` | `100000` | Max internal steps |
| `ref_rtol` / `ref_atol` | `1e-10` / `1e-20` | Reference (if enabled) |
| `num_steps` | synced from `policy.num_steps` | RL re-query period |

Observation flags (`use_prev_state`, `use_gradient_only`) are **injected from `policy`** into the solver config so the pipeline and the selector stay consistent—you do not set them under `solver`.

---

## `conditions` *(required, non-empty list)*

Each entry:

| Field | Required | Description |
|-------|----------|-------------|
| `temp` | yes | Initial temperature [K] |
| `pressure_atm` | yes | Pressure [atm] (converted to Pa for Cantera) |
| `Z` | one of Z / phi | Mixture fraction |
| `phi` | one of Z / phi | Equivalence ratio |
| `dt` | yes | Integration timestep [s] |
| `t_end` | yes | Final time [s] |
| `label` | no | Display name for plots / CSV |

```yaml
conditions:
  - label: MidT_MidP
    temp: 800
    pressure_atm: 10.0
    Z: 0.062
    dt: 1.0e-6
    t_end: 3.5e-3
```

Choose `dt` / `t_end` so ignition is resolved (low-\(T\) cases often need larger `dt` and longer `t_end`).

---

## `output` block *(optional)*

```yaml
output:
  dir: handoff_runs/my_run
  save_pkl: true
  save_summary_csv: true
  plot:
    enable: true
    style: comparison
    compare_methods: null          # or [CVODE, QSS, RL-Adaptive]
    species: [OH, CO2, H2O]
    formats: [png, pdf]
    dpi: 300
```

| Field | Default | Meaning |
|-------|---------|---------|
| `dir` | `handoff_runs/default` | Output directory (created if missing) |
| `save_pkl` | `true` | Write per-condition pickles |
| `save_summary_csv` | `true` | Write `summary.csv` |
| `plot.enable` | `true` | Generate figures |
| `plot.style` | `comparison` | Currently only `comparison` is implemented |
| `plot.compare_methods` | `null` (= all run methods) | Overlay subset on figures |
| `plot.species` | `[OH, CO2, H2O]` | Up to three species panels (log₁₀ mass fraction) |
| `plot.formats` | `[png, pdf]` | Image formats |
| `plot.dpi` | `300` | Raster resolution |

Species missing from the mechanism are skipped (empty panel).

---

## `--set` override syntax

```text
section.subsection.key=value
```

Examples:

```bash
--set device=cuda
--set policy.num_steps=50
--set policy.use_gradient_only=true
--set "output.plot.formats=[png]"
--set n_repeats=5
```

Parsed types: booleans (`true`/`false`), `null`, ints, floats, comma-lists in `[...]`, else string.

In **zsh**, always quote list overrides: `--set "output.plot.formats=[png]"` (otherwise the shell expands `[png]`).

---

## Validation errors you may see

| Message | Fix |
|---------|-----|
| `Missing required field 'policy.model_path'` | Set the checkpoint path |
| `RL checkpoint not found` | Fix path / run from repo root |
| `methods must include 'RL-Adaptive'` | Add it to `methods` |
| `methods includes 'Supervised-ML' but supervised.model_dir is not set` | Add `supervised.model_dir` or remove Sup-ML from `methods` |
| `conditions[i] must set either 'Z' or 'phi'` | Add mixture specification |
| `Unknown method(s)` | Typo in method name |

 # E18 campaign summary — method, trials, results, next steps

Living cross-reference for the OpenFOAM RL chemistry solver-selection project, with emphasis on the **E18 opposed-jet** campaign (Jul 2026). Complements the pedagogical wiki and the engineering logs.

| Doc | Role |
|-----|------|
| [`docs/wiki/01_reacting_flow_and_solver_selection.md`](../../../docs/wiki/01_reacting_flow_and_solver_selection.md) | Equations, chemFoam, mechanism, RL modes (onboarding) |
| [`docs/wiki/README.md`](../../../docs/wiki/README.md) | Wiki index |
| [`AGENTS.md`](../../../AGENTS.md) | Docker / Foam / guard footguns |
| [`OPENFOAM_PATH/DECISIONS.md`](../../DECISIONS.md) | Dated design decisions |
| [`THESIS_NOTES.md`](../../../THESIS_NOTES.md) | Committee narrative (frozen findings) |
| [`OPENFOAM_PATH/instruction.md`](../../instruction.md) | Full implementation spec |
| [`e17_2/E17_2_GATES.md`](../e17_2/E17_2_GATES.md) | Guarded QSS/RL CFD modes |
| [`e17_2/FORENSICS.md`](../e17_2/FORENSICS.md) | E17 post-ignition SIGFPE forensics |
| This file + [`README.md`](README.md) | E18 stage status |

---

## 1. Goal and method (big picture)

**Goal.** Deploy a 0D-trained PPO policy that chooses **CVODE vs α-QSS (CHEMEQ2)** per cell inside OpenFOAM reacting flow, **zero-shot**, on Luo n-dodecane (106 species / 678 reactions), and demonstrate it on a 2D opposed jet that is cross-checkable against Ember 1D.

**Method stack**

1. **Mechanism pipeline** — Cantera YAML → Chemkin → `chemkinToFoam`; production thermo = **Option R** shared JANAF breakpoints (`Thigh=3500`). See `mechanisms/CONVERSION.md`, `DECISIONS.md` (2026-07-17).
2. **Integrators** — SUNDIALS CVODE + CHEMEQ2 QSS as Foam chemistry solvers; custom **`method rl`** (`rlChemistryModel`) embeds both + policy + guards.
3. **Parity ladder** — rates → 1 µs step → 0D chemFoam → 2D flame (`instruction.md` ground rules).
4. **Policy interface** — 19-D obs (`T_norm`, 8×`log10 Y_key`, `P_norm`, 9×Δlog10); actions 0=CVODE / 1=QSS; conf&lt;0.6→CVODE; τ_dec = `numSteps×dtRef` (E16.5 chemistry-time clock).
5. **CFD coupling** — chemistry returns effective **RR**; energy uses **Qdot**; diagnostic `Tconsistency` / `solverFlag` / `chemCpuTime` / `qssFallbackCount`.

Pedagogical walkthrough: [wiki §1–5](../../../docs/wiki/01_reacting_flow_and_solver_selection.md).

---

## 2. What we built before E18 (context)

### 2.1 Thermo and QSS instrument (E10–E15)

| Episode | Outcome | Pointer |
|---------|---------|---------|
| Option R thermo refit | Fixed blended-NASA collapse after ignition | `THESIS_NOTES.md`, `DECISIONS.md` |
| E13–E14 QSS Teq offset | Element drift ≠ energy bug; gate reframed | `THESIS_NOTES.md`, `e14_*` |
| E15 CONFORM | Production QSS = T-freeze + fixed coeffs | tag `validation-baseline-v1` |

### 2.2 Policy wiring (E16)

| Gate | Outcome |
|------|---------|
| E16.1 | Interface freeze (ckpt / TS / manifest hashes) |
| E16.3b–E16.4 | Teacher-forced parity; free-run accuracy vs cvodeOnly |
| E16.5 | **τ_dec clock** ≠ CFD Δt (unblocks adaptive CFD) |

### 2.3 First 2D smoke (E17)

- Case: `opposedJet_2D` (L=0.02 m).
- **cvodeOnly** completed; **qssOnly / rlAdaptive** SIGFPE after ignition (T→3500).
- **E17.2:** unguarded stock QSS retired for CFD; guards Layer-1/2 + CVODE fallback. See `e17_2/FORENSICS.md`.

---

## 3. E18 campaign — what we tried and decided

### 3.1 Stage 0 — ignition viability (DONE)

Cantera MRM scout over strain × T_air × p.

| Pick | Value |
|------|-------|
| p | **10 atm** (not 1 atm) |
| T_air | **1000 K** |
| a | **100 s⁻¹** |
| τ_ign · a | ≈ 0.14 (comfortable) |

Report: [`stage0_scout/STAGE0_REPORT.md`](stage0_scout/STAGE0_REPORT.md) · Decision: `DECISIONS.md` 2026-07-20.

### 3.2 Stage 1 — cold mixing (DONE)

| Item | Choice / result |
|------|-----------------|
| Geometry | Ember-matched **L=0.008 m**, V=±**0.4 m/s** (not E17’s 0.02 m / 1 m/s) |
| Mesh | 20 000 cells (200×100), mid refined |
| Chemistry | OFF to freeze **t=0.05 s** |
| Stagnation | Ux=0 at x≈**0.00622 m** (ρ mismatch; expected) |
| **alphaEff** | Was **identically zero** — Sutherland `As=Ts=0` in thermo/transport. Patched to air-like As/Ts. Confirmed nonzero μ, α. |

Report: [`stage1_cold/STAGE1_REPORT.md`](stage1_cold/STAGE1_REPORT.md) · Case: `cases/opposedJet_E18/`.

### 3.3 Stage 2 — chemistry restart (PARTIAL → RL COMPLETE)

Base dump: `stage2_chem_20260720_130353/` (gitignored; scripts tracked).

| Mode | Status | Notes |
|------|--------|-------|
| **cvodeOnly** | User-stopped ~**0.055** | Ignited (Tmax~2500 K); ~3 min wall/step; flame stays air-side (Z*~0.12) |
| **rlAdaptive** (wrong policies) | Stopped / deleted | See §3.4 |
| **rlAdaptive** (`lambda_1p0_with_base_obs_rms`) | **COMPLETED** `0.05→0.059` | `wall_s≈326812` (~90.8 h), `exit=0`, `End` |
| **qssOnly** | Not run as full twin | Guaranteed next for usage/accuracy fork |

Scripts: `stage2_configure_mode.sh`, `stage2_run_one.sh`, `stage2_chem_restart.sh`.

### 3.4 Policy swap trials

| Checkpoint | Result |
|------------|--------|
| Prior production `best_offline_eval2` → `policy.ts` | Baseline used in early RL attempt |
| `finetuned_1D_policy6.pt` | Exported; first restart **FATAL** — Foam manifest used camelCase (`obsRmsMean`) → empty `obs_rms`. Fixed to snake_case (`obs_rms_mean` / `obs_dim`). Run deleted as wrong model. |
| `lambda_1p0_with_base_obs_rms.pt` | Official path: `rlEnv` + `tools/export_policy.py` + `export_policy_manifest_foam.py`. Includes obs_rms. **Production for completed RL run.** |

Footgun recorded: `AGENTS.md` §4.4 / changelog 2026-07-22.

### 3.5 Guard threshold trials (same campaign)

| Setting | Observation |
|---------|-------------|
| `epsY=1e-12`, `epsSumY=1e-3`, `TminAccept=310` | ~90% cells `fallbackCVODE` |
| + `rlFallbackReasons` logging | **100% `T_bounds`** — fuel T=300 K &lt; 310 K (not Y/ΣY) |
| `epsY=1e-8`, `epsSumY=1e-2`, `TminAccept=250` | First step: **QSS≈19046, fallback=0**, wall_chem ~55 s (was ~182 s) |

Defaults updated in `stage2_configure_mode.sh` and `E17_2_GATES.md`. Remaining late-run fallbacks are almost entirely **`qss_integ`**.

### 3.6 Instrumentation / ops

- `rl_usage_step.csv`: `cpu_*_sum` = MPI-sum CPU-seconds; `wall_chem` = max over ranks; `nProcs`.
- `solverFlag` AUTO_WRITE (0=CVODE, 1=QSS); ParaView via `.foam` + reconstruct of key fields.
- DebugSwitches / SIGFPE hygiene per `AGENTS.md`.
- Gitignore: `stage2_chem_*/`, logs, `processor*`, animations — keep scripts + small reports only.

---

## 4. Results (what we know now)

### 4.1 Physics / setup

- Cold mix + corrected transport yields a usable freeze field with ignition-ready mixture near Z≈0.12.
- On chem restart, flame sits toward the **air (right)** side — consistent with Stage 0 Z* and unequal densities at equal |V|.
- Corner O2 artifacts on fuel-side outlets noted (inletOutlet backflow `inletValue`) — optional BC cleanup.

### 4.2 RL run (`lambda_1p0`, guarded)

- **Completed** freeze→`endTime=0.059` (~9 ms chem window) on 8 ranks / 20k cells.
- Wall clock ~**91 h**; chemistry `wall_chem` typically O(1–4 min) per step once hot (log).
- Progress shows mostly QSS head-counts with small CVODE + rare `qss_integ` fallbacks — **but see §4.3**.

### 4.3 Usage logging (fixed 2026-08-20)

`rlUsage` now prints **both**:

- `policyCVODE` / `policyQSS` — last τ_dec policy action (`policyFlag` field)
- `effCVODE` / `effQSS` — integrator actually used (`solverFlag` field)
- `fallback` / `holdCVODE` — rescue this step / still holding CVODE until next decision

After a QSS→CVODE rescue, policy is **kept**; `forceCvodeHold` forces CVODE until the next τ_dec (no longer overwrites `lastDecision`). Rebuild `librlChemistryModel` to pick this up. Per-cell `rl_decisions.csv` is **off** by default (`logDecisions false`).

### 4.4 Cost and accuracy vs cvodeOnly through shared cutoff (workstation)

Operator killed **cvodeOnly** at **t ≈ 0.05507** (`wall.txt`: `killed_by_user`). Compare both modes through last common time **t = 0.0550667** (same freeze, 20k cells, 8 ranks):

| Metric | cvodeOnly | rlAdaptive (`lambda_1p0`) |
|--------|----------:|--------------------------:|
| Foam ClockTime to cut | ≈ **45.4 h** (163396 s) | ≈ **32.0 h** (115211 s) → **~1.42×** wall |
| Σ chemistry CPU-seconds (MPI-sum) | ≈ **223 h** | ≈ **59 h** → **~3.8×** less |
| Progress steps in window | 620 | 679 (adaptive Δt differs) |
| First T_max ≳ 1100 K | ≈ 0.0540 s | ≈ 0.0536 s (**~0.4 ms earlier**) |
| Peak recorded T_max ≤ cut | ≈ 2529 K | ≈ 2541 K |
| Post-flame \|ΔT_max\| (t≥0.0545, sparse) | — | mean ~**15 K**, max ~**41 K** |

**Caveats.** (1) Not a centerline/field RMSE gate. (2) `rlUsage` cell counts vs `solverFlag` still inconsistent after step 1 — do not quote QSS% from the log alone. (3) Full-horizon cvodeOnly twin and qssOnly twin pending **cluster** runs.

### 4.5 Cluster status (in progress, 2026-08-20)

Heavy-compute **cvodeOnly** and **rlAdaptive** twins on the cluster are in progress to finish matched horizons to **0.059**, support hard accuracy gates, and supersede the workstation kill-time comparison.

**Production entry point (do not dump into `validation/`):**
[`OPENFOAM_PATH/production/`](../../../production/) — see [`RUN_PLAN.md`](../../../production/RUN_PLAN.md), `scripts/20_run_chem.sh`, `cluster/*.sbatch`.

Document results under `production/runs/` extracts and freeze a follow-on paragraph in `THESIS_NOTES.md` when cluster dumps land.

---

## 5. Next steps (recommended order)

1. **Cluster twins** — use [`production/`](../../../production/) (`RUN_PLAN.md`); finish cvodeOnly + rlAdaptive + qssOnly to `endTime=0.059`.
2. **Fix usage logging** — print both `lastDecision` (policy) and final `solverFlag` (effective) every step; rebuild `librlChemistryModel`.
3. **Accuracy gate** — centerline / field RMSE vs cluster cvodeOnly (T, OH; E16 standing condition).
4. Optional: **τ_dec = Δt** ablation; outlet `inletValue` polish; Ember centerline package.
5. Update `THESIS_NOTES.md` when cluster accuracy/cost tables are frozen.

---

## 6. Quick path map

```text
OPENFOAM_PATH/
  cases/opposedJet_E18/          # production geometry + freeze IC
  cases/chemFoam_0D/             # 0D parity harness
  policy/policy.ts + policy_manifest   # active lambda_1p0 export
  src/rlChemistryModel/          # method rl + guards + usage
  validation/zeroD/
    e18_prep/                    # this campaign (scripts + reports)
    e17_2/                       # guards / forensics
    e17_remote/                  # smoke kit
docs/wiki/                       # onboarding equations + RL
AGENTS.md · DECISIONS.md · THESIS_NOTES.md · instruction.md
```

---

## 7. One-paragraph abstract

We completed the OpenFOAM instrument for CVODE/QSS with RL dispatch (parity through E16, guarded CFD after E17.2), then ran an Ember-matched opposed-jet campaign (E18): viability scout → cold mix with a transport bugfix → chemistry restart. After correcting policy export/manifest keys and relaxing guard `TminAccept` for 300 K fuel, a full **rlAdaptive** trajectory with `lambda_1p0_with_base_obs_rms` finished the 9 ms chem window. Through the workstation cvodeOnly kill time (**t ≈ 0.05507**), RL was ~**1.4×** faster wall and ~**3.8×** lower chem CPU-sum, with ~**0.4 ms** earlier ignition and post-flame **T_max** within tens of kelvin — interim only. Remaining work is logger/field consistency, **cluster** cvodeOnly/RL twins to 0.059, qssOnly, and centerline accuracy packaging versus Ember.

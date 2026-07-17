# RL Solver Selection in OpenFOAM — 2D Extension: Implementation Specification

**Target:** Deploy the existing 0D-trained PPO solver-selection policy (CVODE vs α-QSS/CHEMEQ2)
inside OpenFOAM reacting-flow simulations, zero-shot (no retraining), and demonstrate it on
2D laminar flames with the n-dodecane mechanism (106 species, Luo — same YAML as the CnF paper).

**Deliverables:** (1) an OpenFOAM chemistry model with per-cell RL solver dispatch,
(2) validated CVODE and α-QSS integrators inside OpenFOAM with proven parity against Cantera,
(3) a 2D opposed-jet case cross-validated against existing Ember 1D results,
(4) a 2D coflow diffusion flame demonstration with speedup/accuracy/solver-map results
against CVODE-only and QSS-only baselines.

**This spec is written for a coding agent (Claude Code). Follow phases in order.
Every phase has acceptance criteria — do not proceed past a phase until they pass.**

---

## 0. Non-negotiable ground rules (lessons from the failed PeleC port)

These rules exist because a previous port of α-QSS into PelePhysics failed in specific,
diagnosed ways. Violating any of these reproduces those failures.

1. **Parity ladder discipline.** Validate in this order, never skipping a rung:
   (a) reaction-rate parity at pinned states → (b) single 1 µs integration-step parity →
   (c) 0D trajectory parity → (d) 1D/2D flame parity. A discrepancy at rung N is
   root-caused at rung N, not compensated downstream.
2. **Never rescale rates to force agreement.** If OpenFOAM's reaction rates disagree with
   Cantera at a pinned state, the cause is units, third-body/pressure-dependent reaction
   handling, thermo fits, or stoichiometry parsing. Find it. Do not introduce correction
   factors — a rescale corrupts the QSS timescales τᵢ and silently breaks the integrator.
3. **α-QSS requires true creation/destruction rates** (qᵢ and dᵢ assembled from forward/reverse
   progress rates per reaction), **not** a sign-split of the net rate
   (q = max(ω̇,0), d = max(−ω̇,0)). The sign-split destroys τᵢ = cᵢ/dᵢ for stiff radicals
   where q ≈ d. This was root cause #1 in Pele.
4. **Absolute vs relative time.** The integrator advances exactly the chemistry window Δt_chem
   it is handed — verify with a unit test that total integrated time equals Δt_chem to
   round-off. (Pele bug: each outer step integrated ~75× too long.)
5. **Energy-path consistency.** Understand exactly how the chemistry model returns its result
   to the transport solver (in OpenFOAM: effective reaction rates RR, from which heat release
   is computed — see §3.2). Log `|T_integrated − T_recovered|` per cell as a standing
   diagnostic. Large gaps = thermodynamic inconsistency between chemistry and CFD.
6. **Chemistry windows ≈ 1 µs.** The policy was trained on ~1 µs decision intervals.
   Case setups must produce chemistry windows of the same order (via CFD Δt or fixed
   sub-stepping). Do not evaluate the policy on 10⁻² s windows.
7. **Single source of truth for the policy interface.** Feature definitions, ordering,
   normalization constants, and the network weights are extracted from the existing training
   repository and serialized once (§5.1). Never re-implement features from a paper
   description or from memory.
8. **Version-pin everything** (OpenFOAM, SUNDIALS, Cantera, LibTorch/ONNX Runtime, mechanism
   files, compiler) in a top-level `VERSIONS.md`. Same container on workstation and HPC.

---

## 1. Repository layout

```
of-rl-chem/
├── VERSIONS.md
├── container/              # Apptainer/Singularity def + build scripts (workstation + LSU HPC)
├── mechanisms/             # dodecane_luo_106.yaml (Cantera) + Chemkin export + conversion log
├── src/
│   ├── qssChemistrySolver/     # α-QSS (CHEMEQ2) — port of the debugged C++ from the Pele work
│   ├── cvodeChemistrySolver/   # SUNDIALS CVODE wrapper
│   ├── rlChemistryModel/       # custom chemistry model: features → batched policy → dispatch
│   └── policyRuntime/          # TorchScript/ONNX loading + batched inference + feature builder
├── validation/
│   ├── rate_parity/        # rung (a): OF rates vs Cantera at pinned states
│   ├── step_parity/        # rung (b): single 1 µs step, OF-QSS & OF-CVODE vs Cantera refs
│   ├── zeroD/              # rung (c): chemFoam ignition-delay curves vs Cantera
│   └── oned_crossref/      # rung (d): 2D planar opposed-jet vs existing Ember results
├── cases/
│   ├── chemFoam_0D/
│   ├── opposedJet_2D/
│   └── coflow_2D/
├── analysis/               # post-processing: metrics, solver maps, figures (Python)
└── tests/                  # unit tests runnable in CI (container)
```

Work in small commits, one per milestone. Keep a `DECISIONS.md` log of every nontrivial choice
(solver settings, tolerances, mesh sizes) with a one-line justification.

---

## 2. Phase 0 — Environment, mechanism, and stock baseline (~1–2 weeks)

### 2.1 Toolchain
- **OpenFOAM:** ESI branch, v2312 (or v2406) — chosen for the templated
  `StandardChemistryModel`/`chemistrySolver` hierarchy and DLBFoam compatibility (§7).
- **SUNDIALS** ≥ 6.x (CVODE), **Cantera** ≥ 3.0 (reference oracle), **LibTorch or ONNX Runtime**
  (CPU build) for policy inference.
- Build an **Apptainer container** with all of the above; verify it runs on both the
  workstation and LSU HPC (check available MPI/interconnect story; use the cluster's
  recommended container-MPI binding approach).

### 2.2 Mechanism import
- Start from the exact Cantera YAML used in the CnF paper (Luo n-dodecane, 106 species).
- Convert to Chemkin format (Cantera's `yaml2ck` / equivalent) and import with
  `chemkinToFoam`. Record every conversion step in `mechanisms/CONVERSION.md`.
- **Do not** substitute a different dodecane mechanism (e.g., a 53-species `dodecane_lu`)
  anywhere in the pipeline. All comparisons are same-mechanism.

### 2.3 Rate parity (parity-ladder rung a) — ACCEPTANCE GATE
- Write a standalone test harness that, for ~200 sampled thermochemical states
  (T ∈ [600, 2800] K, p ∈ [1, 60] atm, mixture fractions spanning fuel-lean to rich,
  including partially-burnt states sampled from Cantera 0D trajectories):
  - evaluates species net production rates ω̇ᵢ AND per-reaction forward/reverse progress
    rates in both OpenFOAM (via the loaded mechanism) and Cantera (via YAML),
  - reports max relative error per species/reaction.
- **Accept:** rates agree to ≤ 0.1% relative (allowing for thermo-fit round-off) across all
  sampled states. Any systematic outlier (specific reactions, e.g., pressure-dependent or
  third-body) is root-caused before proceeding (ground rule 2).

### 2.4 Stock baseline
- Run stock `reactingFoam` (or the ESI reacting solver of that version) on a small 2D case
  with the built-in `ode` chemistry solver (seulex) and the imported mechanism, just to
  confirm the mechanism/thermo/transport files run end-to-end. No physics claims from this.

---

## 3. Phase 1 — Integrators inside OpenFOAM (~2–3 weeks)

### 3.1 α-QSS (CHEMEQ2) solver
- Port the **already-debugged C++ CHEMEQ2** from the Pele effort into an OpenFOAM
  `chemistrySolver` (or a callable used by the custom chemistry model, §5.2).
- Requirements (all unit-tested):
  - qᵢ/dᵢ from true per-reaction forward/reverse progress rates (ground rule 3);
  - integrates exactly Δt_chem (ground rule 4);
  - internal sub-stepping and α-QSS corrector settings identical to the Cantera/Ember
    reference implementation (same ε, same iteration count);
  - float64 throughout.

### 3.2 CVODE solver
- Wrap SUNDIALS CVODE (BDF, Newton, **dense finite-difference Jacobian — same configuration
  as the Cantera reference in the paper**) as the "robust" arm.
- rtol/atol identical to the paper's 0D/1D setup.
- Note on coupling: in the ESI `StandardChemistryModel`, `solve(deltaT)` integrates each
  cell's composition over the chemistry window and stores **effective rates**
  RRᵢ = ρ(Yᵢⁿ⁺¹ − Yᵢⁿ)/Δt, which the transport equations then consume; heat release is
  computed from RR and enthalpies of formation. This sidesteps the Pele energy-path trap
  (no integrated-T handoff), but implement the standing diagnostic anyway:
  after transport applies RR, compare the resulting cell T against the integrator's final
  internal T; log the max/mean gap per step (ground rule 5).
- Decide and document whether chemistry integration is done at constant pressure with
  T evolved from energy (matching the 0D training environment: constant-pressure reactors)
  — match the model's assumption to what the policy saw in training as closely as the
  OpenFOAM chemistry-model structure allows, and record the residual mismatch in
  `DECISIONS.md`.

### 3.3 Single-step parity (rung b) — ACCEPTANCE GATE
- For ~50 pinned states (must include the known hard case from the Pele report:
  ~800 K, 10 atm, Z ≈ 0.062), advance exactly one 1 µs step:
  - OF-QSS vs the Python/Cantera-QSS reference (**including its known flaws** — the target
    is bit-level algorithmic parity, not "better");
  - OF-CVODE vs Cantera-CVODE at matched tolerances.
- **Accept:** species/T after the step agree to solver round-off (QSS: relative differences
  explained entirely by float noise; CVODE: within tolerance-consistent bounds).

### 3.4 0D trajectory parity via chemFoam (rung c) — ACCEPTANCE GATE
- Use OpenFOAM's `chemFoam` (single-cell 0D reactor) to run constant-pressure ignition for
  a grid of initial conditions matching the paper's 0D evaluation set
  (T₀ ∈ {750, 800, 1000} K crossed with p ∈ {10, 30, 60} atm at minimum).
- **Accept:**
  - OF-CVODE ignition delays within 1% of Cantera-CVODE;
  - OF-QSS reproduces Cantera-QSS trajectories including its characteristic ignition-delay
    overprediction (13–45% vs CVODE) — deviation from *Cantera-QSS* itself ≤ 1%;
  - CPU-cost ratio QSS:CVODE per step in OpenFOAM is in the same regime as in
    Cantera/Ember (QSS meaningfully cheaper). If QSS is *not* cheaper here, stop and
    profile — that is a port bug (RHS assembly, memory allocation in the hot loop), not
    a property of the algorithm.

---

## 4. Phase 2 — Policy runtime and feature parity (~1–2 weeks)

### 4.1 Export the trained policy (single source of truth)
- From the existing training repo, export:
  - the PPO policy network → TorchScript (preferred) or ONNX;
  - the **exact feature pipeline**: feature list, ordering, any temporal-gradient
    definitions (including the finite-difference stencil and the Δt they assume),
    normalization constants — serialized to a versioned JSON alongside the model file.
  - the deterministic action rule used at deployment (e.g., argmax vs threshold on
    the action probability) — must match what was used for the Ember 1D results.
- If any feature is a *temporal* gradient, the OpenFOAM implementation must maintain the
  required per-cell history buffers (previous chemistry-window states) with the same Δt
  semantics as training. Document this precisely.

### 4.2 Feature/decision parity test — ACCEPTANCE GATE
- Take ≥ 20 recorded 0D trajectories from the training/eval set (states saved every
  decision interval). Feed the recorded states through the new C++ feature builder +
  exported policy. Compare per-step decisions against the Python pipeline's decisions.
- **Accept:** ≥ 99.9% decision agreement; every disagreement traced to float noise at a
  probability ≈ 0.5 boundary, not to feature mismatch.

### 4.3 Batched inference
- Architecture: once per CFD step (or per chemistry call), gather feature vectors for all
  cells into a contiguous buffer → single forward pass (LibTorch/ONNX, CPU, intra-op
  threads pinned sensibly under MPI) → scatter a per-cell `solverFlag` field.
- Measure and log inference overhead as % of chemistry wall time.
  **Target: < 3%** at ~10⁵ cells (the 1D paper achieved ~0.01–2.7%).
- The `solverFlag` field must be writable as a volScalarField for visualization
  (this is your solver-map figure).

---

## 5. Phase 3 — The RL-adaptive chemistry model and 2D cases (~3–4 weeks)

### 5.1 `rlChemistryModel`
- Subclass/replicate `StandardChemistryModel` so that `solve(deltaT)`:
  1. builds features for all cells (using per-cell history buffers as required),
  2. runs batched policy inference → per-cell decision,
  3. per cell, dispatches to OF-QSS or OF-CVODE for the chemistry window,
  4. computes RR as usual; writes `solverFlag`, per-cell chemistry CPU time
     (for load-imbalance analysis), and the T-consistency diagnostic.
- Runtime-selectable modes via dictionary: `rlAdaptive | cvodeOnly | qssOnly`
  (baselines use the identical code path minus the policy).
- Sub-stepping control: expose `maxChemDeltaT` (default 1 µs) so the chemistry window seen
  by the policy matches training even if the CFD Δt is larger; decisions are made per
  sub-window per cell.

### 5.2 Case A — 2D planar opposed-jet (rung d: cross-code validation)
- Reproduce the Ember 1D counterflow configuration as a 2D planar opposed-jet:
  n-dodecane fuel side at 300 K, air at 800 K, strain rates spanning 10–2000 s⁻¹
  (start with one moderate value, e.g., 500 s⁻¹), domain sized to match the Ember setup
  along the axis.
- Purpose: the centerline solution should reproduce the known Ember/1D results,
  cross-validating the entire OpenFOAM stack (transport + chemistry + policy) against
  published numbers before making any new claim.
- **Accept:** RL-adaptive centerline T/species vs OF-CVODE reference: RMSE in the same
  range as the 1D paper (T RMSE ≲ 10 K); CVODE-usage fraction and spatial localization
  qualitatively consistent with the 1D solver maps (CVODE band at the reaction zone,
  single-digit % usage); speedup vs OF-CVODE reported.

### 5.3 Case B — 2D coflow diffusion flame (the new result)
- Configuration: axisymmetric or planar 2D laminar coflow, gaseous n-dodecane jet into
  hot air coflow (coflow T chosen for autoignition, e.g., 900–1100 K — sweep to find a
  robust igniting condition), atmospheric or mildly elevated pressure.
- Mesh: start ~30–60k cells (structured, refined at the shear layer), production runs up
  to ~100–200k cells. CFD Δt such that chemistry windows are ~1 µs (with sub-stepping
  as a safety net).
- Runs: `cvodeOnly` (reference), `qssOnly`, `rlAdaptive` — identical mesh/Δt/tolerances.
- Transient of interest: autoignition kernel formation → flame stabilization. This gives
  the compelling spatiotemporal story (stiff ignition front sweeping through the domain,
  CVODE band tracking it).

### 5.4 Metrics and figures (define before running production cases)
- Accuracy: T and major/radical species (OH, H₂O, CO₂) RMSE fields vs `cvodeOnly`;
  ignition time of the kernel; stabilized flame liftoff height/position.
- Cost: total wall time, chemistry-only wall time, speedup vs `cvodeOnly`; policy-inference
  overhead %; CVODE-usage fraction (space–time).
- Solver maps: `solverFlag` snapshots at 4–6 times through ignition + a space–time
  composite along a representative line.
- Robustness: `qssOnly` failure signature (delayed/failed ignition) as the motivating
  contrast, exactly as in the 0D/1D chapters.
- Per-cell chemistry CPU-time field → load-imbalance quantification (max/mean per rank).

---

## 6. Phase 4 — Parallel performance and analysis (~2 weeks)

- Scaling runs on LSU HPC: 1 → N nodes for Case B; report chemistry load imbalance
  induced by adaptive selection (expensive CVODE cells cluster at the front).
- **Optional but high-value:** integrate or emulate DLBFoam-style dynamic load balancing of
  chemistry cells across ranks and report the additional wall-time gain. If time is short,
  quantify the imbalance and cite load balancing as the engineering remedy — the
  measurement alone is a contribution.
- Sensitivity spot-checks: one tolerance variation on CVODE, one coflow temperature
  variation — enough to answer committee "is this robust?" questions.
- Freeze results; export all figures with scripts in `analysis/` (fully reproducible from
  raw case data).

---

## 7. Risks and fallbacks (pre-agreed, so the agent doesn't improvise)

| Risk | Signal | Fallback |
|---|---|---|
| SUNDIALS↔OpenFOAM wrapping friction | Phase 1 slips > 1 week | Use OpenFOAM's built-in `seulex` as the robust arm **only as a stopgap for plumbing tests**; the thesis result must use CVODE (policy cost model was trained against CVODE). |
| Rate parity failures on specific reactions | Rung (a) outliers | Root-cause per reaction class (third-body, PLOG, Troe). Never rescale. If a Chemkin-conversion limitation is proven, fix the conversion, not the rates. |
| Feature mismatch (temporal gradients) | Rung 4.2 disagreements | Reduce to the exact recorded-trajectory replay; diff feature-by-feature; fix the C++ builder. Do not retrain or re-threshold the policy to "make it work". |
| Coflow case won't autoignite robustly | No kernel across coflow-T sweep | Add a small hot-spot initialization (documented), or pilot the flame; physics choice logged in `DECISIONS.md`. |
| 2D runs too slow for iteration | Case B > 24 h on workstation | Iterate on a half-resolution mesh; production on HPC only. |
| Policy behaves pathologically out-of-distribution (2D states unlike 0D/1D) | Excess CVODE usage or instability with QSS | This is a *finding*, not a failure — characterize it (which states, which features saturate), report it honestly; optional mitigation: default-to-CVODE guard on out-of-range features. |

---

## 8. Definition of done (thesis-chapter level)

1. Parity ladder fully green (rungs a–d) with archived test outputs.
2. Case A reproduces 1D-consistent behavior in OpenFOAM (cross-code validation table).
3. Case B: RL-adaptive achieves a reported speedup vs CVODE-only at near-reference accuracy,
   with QSS-only shown inaccurate, solver maps physically interpretable, inference overhead
   < 3%, all on the 106-species mechanism.
4. Parallel imbalance quantified (DLBFoam integration optional).
5. Every figure regenerable by one script; container + versions archived on HPC storage.

**Indicative timeline: ~9–11 weeks total.** Phases 0–1 are the schedule risk; protect them.
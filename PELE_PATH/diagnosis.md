# Static Code Inspection Brief: Diagnose QSS Integrator Failure in PelePhysics Fork

## Context (read first)

I am a combustion/RL researcher. I built a reinforcement-learning policy that switches between two chemistry integrators — CVODE (implicit BDF, from SUNDIALS) and an α-QSS predictor-corrector scheme (Mott, Oran & Van Leer 2000) — per cell, per timestep. This worked correctly in:

- **0D**: constant-pressure homogeneous ignition via Cantera (Python), n-dodecane 106-species mechanism. QSS accurate and fast.
- **1D**: counterflow diffusion flames via the Ember code, Strang operator splitting. QSS accurate and fast.

I then ported the α-QSS integrator into **PelePhysics** (my fork: `elotech47/PelePhysics`, branch `development`) as a reactor so it can be used inside PeleC / PeleLM-eX for a 2D counterflow diffusion case. **In Pele, QSS fails**: it either destabilizes, produces wrong solutions, or crashes — even when manually forced on. CVODE in the same setup works. I need to know whether the bug is in my port or in a structural mismatch between what α-QSS assumes and what the Pele reactor interface provides.

You likely **cannot compile or run** anything — the workstation with the build environment is elsewhere. Do everything via static reading of the code. If you can build/run a tiny standalone C++ file with no AMReX dependency, that is a bonus (see Task 7), but do not block on it.

## What α-QSS structurally requires (so you know what to look for)

The α-QSS scheme splits each species ODE into non-negative **production** q_i and **destruction** d_i terms:

    dy_i/dt = q_i(y,T) − d_i(y,T),  with d_i ≥ 0, q_i ≥ 0

It defines a per-species timescale via d_i/y_i, a stiffness ratio τ_i = (d_i/y_i)·Δt, and an interpolation parameter α_i(τ_i) ∈ [0.5, 1] used in a predictor-corrector Padé update. Key structural assumptions:

1. q and d are the **true separated creation/destruction rates** from the reaction mechanism — not a reconstruction from net rates (e.g., `q = max(ω̇,0), d = max(−ω̇,0)` is WRONG in stiff regions: a species can have huge q and d that nearly cancel, and the net-rate reconstruction destroys the timescale information τ_i depends on).
2. It divides by y_i, so it needs floors on species values.
3. It is a pure-kinetics scheme. It has **no native concept of an external forcing/source term**. Pele reactors, however, integrate `dY/dt = ω̇ + F_ext` where `F_ext` (variables typically named like `rY_src_ext`, `rEner_src_ext`, or similar) is the frozen advection-diffusion forcing over the chemistry advance. F_ext can be negative and can dominate kinetics in near-inert cells.
4. It needs correct coupling to the energy/temperature equation in the SAME formulation Pele uses (see Task 4).

## Repo landmarks

- My QSS reactor implementation: search the fork for it. Likely under `Reactions/` alongside the stock reactors. Stock reactors to compare against: `ReactorCvode` (implicit reference) and `ReactorRK64` (the existing **explicit** reactor — this is the gold-standard template for how an explicit integrator is supposed to handle forcing terms, energy, units, and the reactor interface in this codebase).
- Mechanism-generated code (CEPTR output): functions computing production rates, e.g. `productionRate(...)`, and whatever separated forward/reverse or creation/destruction routines exist. Check what my QSS code actually calls.
- PelePhysics uses **CGS units** internally (g, cm, s, erg, mol/cm³) and mixes mass-based and molar quantities. Cantera (my reference implementation) is SI/kmol-based.
- There may also be my original working Python α-QSS implementation or a standalone C++ port somewhere in the repo (search for `alpha`, `qss`, `pade`, `predictor`, `corrector`). If found, use it as the behavioral reference.

## Tasks, in priority order

Work through these in order. For each, report: finding, evidence (file:line), verdict (BUG / SUSPICIOUS / OK), and severity.

### Task 1 — External forcing term handling (top suspect)

Find every place `ReactorRK64` and `ReactorCvode` consume the external source arrays (`rY_src_ext`, `rEner_src_ext` or equivalents — identify the actual names). Then check my QSS reactor:

- Does it read these arrays at all? If it **ignores** them → BUG (solution drifts; chemistry integrates the wrong ODE; symptoms look like "QSS is inaccurate").
- If it **includes** them, HOW? If forcing is folded into q_i/d_i (e.g., negative forcing added to d, or forcing added to q where it can be negative) → BUG (breaks the non-negativity assumptions and corrupts τ_i).
- The defensible pattern: treat forcing as an explicit additive increment per substep, separate from the q/d kinetic update; or add non-negative forcing to q and handle negative forcing as d-like ONLY via F/y_i with strong floors. Note which pattern (if any) is implemented.
- Also check the **energy** forcing: is `rEner_src_ext` applied to the temperature/energy update consistently with how RK64 does it?

### Task 2 — Construction of q_i and d_i

Trace exactly how my QSS code computes production and destruction rates:

- Which mechanism function does it call? Does that function return separated creation/destruction (or forward/reverse per-reaction rates that are then assembled into per-species q and d), or does it return **net** ω̇?
- If q/d are reconstructed from net rates → BUG (see structural note above). This alone fully explains "worked in Cantera (which exposes `creation_rates`/`destruction_rates`) but fails in Pele."
- If per-reaction forward/reverse rates are assembled: verify stoichiometric bookkeeping — a species consumed by the forward direction of reaction j must land in d_i, produced in q_i, and reversible reactions must be split by direction, not netted per reaction.
- Check for third-body / pressure-dependent reaction handling differences between the paths.

### Task 3 — Units audit

Line-by-line audit of every physical quantity crossing between my QSS code and PelePhysics:

- Concentrations: mol/cm³ (CGS) vs kmol/m³ (SI). Mass fractions vs molar concentrations vs mass densities (ρY).
- Note that Pele reactors often evolve **ρY_i** (mass density of species), not Y_i. If my Padé update is written for Y_i or molar concentration but is fed ρY_i (or vice versa), τ_i and the update are wrong. Identify the actual state variable my reactor evolves and confirm the QSS update formulas match it.
- Rates: does `productionRate` return mol/cm³/s? What does my q/d assembly assume?
- Energy: erg vs J; cp/cv units; molecular weight conventions (g/mol).
- Look for suspicious magic constants (1e3, 1e6, 1e7, 4.184, 8.314 vs 8.314e7) that indicate partial conversions.

### Task 4 — Energy formulation

My original 0D implementation was **constant-pressure** (h/cp-based temperature equation). Pele reactors have a `reactor_type` concept: energy-based (constant volume / internal energy, e/cv) for PeleC, enthalpy-based for PeleLM-eX.

- Which formulation does my QSS reactor's temperature update implement? Does it branch on reactor type like RK64/Cvode do?
- If it hardcodes constant-pressure cp-based heat release inside a UV reactor (or ignores the reactor_type flag) → BUG (temperature feedback is inconsistent; errors self-amplify through ignition).
- Also check how T is recovered from the evolved energy variable each substep (iterative T-from-e/h solve?) and whether my code skips or reimplements it inconsistently.

### Task 5 — Robustness guards and substepping

- Floors/clipping: is there a floor on y_i before dividing (e.g., 1e-20 level)? Clamps on τ_i? Guards against negative mass fractions arriving FROM the transport step (2D cells legitimately arrive with small negative Y)?
- NaN handling: if one cell NaNs, does anything catch it or does it silently propagate?
- Substepping: how is the internal QSS substep chosen relative to the outer chemistry Δt handed in by Pele? Compare against my reference implementation if found in-repo. If the reactor takes the full outer Δt in one α-QSS step in flame-zone cells → SUSPICIOUS. Is there an error-controlled or timescale-controlled substep loop, and does it match the reference?
- Predictor-corrector iteration count and convergence criterion — do they match the reference implementation?

### Task 6 — Interface conformance diff vs ReactorRK64

Produce a side-by-side structural diff of my QSS reactor against `ReactorRK64`: function signatures, which arrays are read/written, box/cell loop structure, GPU lambda usage (if any), how `react()` returns cost, how the updated state is written back. Flag anything RK64 does that mine skips. RK64 is the existing proof that an explicit integrator can live correctly in this interface — every divergence from it is a lead.

### Task 7 — (Bonus, only if trivially possible) Standalone repro harness

Without AMReX: if the mechanism-generated C++ files and my QSS core are separable, write a small standalone `main.cpp` sketch (do not need to run it) that:
1. Sets a single thermochemical state (T=800 K, p=10 atm equivalent in CGS, a dodecane/air composition).
2. Calls my q/d assembly and prints q_i, d_i, τ_i for the 8 key species (OH, O, H, HO2, H2O, H2, O2, N2).
3. Does the same via a net-rate reconstruction for comparison.
Even as a non-compiled sketch, structuring this will surface interface mismatches. If you CAN compile and run it without AMReX, do so and report the q/d comparison.

## Deliverable

A single markdown report containing:

1. **Root-cause verdict**: the single most likely cause, with file:line evidence, plus ranked runner-ups.
2. **Findings table**: one row per task — verdict, severity, evidence.
3. **Minimal fix plan**: ordered, smallest-diff-first patches. For each: what to change, where, estimated risk.
4. **Instrumentation patch**: a concrete code snippet (ready to drop in) that dumps failing-cell state to a file — T, p/ρe, all Y_i, F_ext arrays, Δt, and the computed q/d/τ for key species — triggered on NaN or on Y outside [−1e−8, 1+1e−8]. I will run this on the workstation later to capture failing states for offline replay.
5. **Open questions** you could not resolve statically, each with the exact experiment (runnable on the workstation) that would resolve it.

## Ground rules

- Do NOT refactor or "improve" code beyond the diagnosis; propose patches in the report instead of applying sweeping changes.
- Cite exact file paths and line numbers for every claim.
- Where my code and the reference reactors disagree, quote both snippets.
- If you find my original working (Python or standalone) QSS implementation in the repo, treat it as the behavioral spec and diff my Pele port against it formula-by-formula (α(τ) expression, predictor, corrector, convergence test).

---

## Report

Static inspection results: **[qss_diagnosis_report.md](qss_diagnosis_report.md)**
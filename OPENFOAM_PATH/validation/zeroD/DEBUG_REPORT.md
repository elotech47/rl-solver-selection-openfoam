# DEBUG_REPORT — chemFoam MidT_MidP post-ignition Newton crash

**Campaign start:** 2026-07-17  
**Container:** `opencfd/openfoam-default:2312`, native `linux/arm64`  
**Case:** `cases/chemFoam_0D` (MidT_MidP: 800 K, 10 atm, Z≈0.062)  
**Mechanism:** Luo n-dodecane 106/678 (thesis mechanism)

## Ground-rule compliance

| Rule                                                       | Status                |
| ------------------------------------------------------------| -----------------------|
| No premature fixes (clip T/h, loosen Newton, rescale heat) | In force              |
| Luo remains production mechanism                           | In force              |
| Revert Thigh→5000 before experiments                       | Done (see Pre-flight) |
| Each experiment logged here                                | Ongoing               |

## Pre-flight — revert Thigh→5000

**What:** Restored original JANAF `Thigh` from Chemkin `mechanisms/chemkin/therm.dat` into
`mechanisms/foam/thermo` and synced to `cases/chemFoam_0D/constant/thermo` (+ expert_repro copy).

| Species | Restored Thigh | Source |
|---------|----------------|--------|
| hcco | 4000 | therm.dat |
| ch3o | 3000 | therm.dat |
| ho2 | 3500 | therm.dat |
| c3h4-a | 4000 | therm.dat |
| (102 others) | 5000 | unchanged |

**Why:** Ground rule 3 — extrapolating NASA-7 beyond fitted range can create negative cp and
contaminate diagnostics.

**Commands:**
```bash
# Targeted StrReplace on mechanisms/foam/thermo for the four species above
cp mechanisms/foam/thermo cases/chemFoam_0D/constant/thermo
cp mechanisms/foam/thermo validation/zeroD/expert_repro/case/constant/thermo
```

**Verified:** `Thigh` histogram = 1×3000, 1×3500, 2×4000, 102×5000.

---

## E1 — Stock-solver control

**Status:** COMPLETE  
**Date:** 2026-07-17  
**Outcome:** Stock **also aborts** in the same h→T Newton during thermal runaway.

### What was run

```bash
# native arm64 container; original JANAF ranges restored
foamDictionary constant/chemistryProperties -entry chemistryType/solver -set ode
# odeCoeffs: seulex, absTol 1e-12, relTol 1e-8
# endTime 0.0035, deltaT/maxDeltaT 1e-6, adjustTimeStep yes
chemFoam
```

Artifacts: `of_runs/MidT_MidP/e1_stock_ode/{log.chemFoam,chemFoam.out,wall.txt,run.log}`

### Raw outcome

| Metric | Value |
|--------|-------|
| exit | 134 (SIGABRT) |
| wall | 94 s |
| IC | p=1.01325e6 Pa, T=800 K, rho=4.63351 |
| Ignition (T≥1200) | t = 2.149e-3 s |
| Last healthy sample | t ≈ 2.27263e-3 s, T ≈ 1850.73 K |
| Fatal | `Maximum number of iterations exceeded: 100` in `species::thermo::T` (h→T Newton), starting from T0=1850.73 |
| Note | `deltaT` had collapsed to ~4e-10 s just before abort |

Same failure mode / phase as custom `cvode` (~1831 K) and `qss` (~1721 K).

### Interpretation

- **H2 (custom RR/Qdot) effectively dead** — stock `ode`/`seulex` hits the identical chemFoam outer-loop failure.
- **H4 (custom RHS thermo-basis mismatch) effectively dead** — stock uses OF's own `derivatives()`.
- **H1 (thermo data) was leading candidate after E1; E2 tests it directly.**
- **H3 (step-size fragility)** still possible as a contributor; stock already had Δt → 4e-10 at crash.

**Next:** E2. Git commit skipped — workspace is not a git repo (`NOT_A_GIT_REPO`).

---

## E2 — Per-species thermo audit vs Cantera

**Status:** COMPLETE  
**Date:** 2026-07-17  
**Outcome:** Foam JANAF matches Cantera YAML to ~3e-5 relative (MW rounding). **No material thermo defects.** Chemkin↔foam coeffs identical.

### What was run

```bash
# After fixing audit bugs (hs ref branch; abs-h jump definition):
rlEnv/bin/python validation/thermo_audit/audit.py
```

Artifacts: `validation/thermo_audit/{thermo_audit.csv,SUMMARY.txt,plots/,run.log,audit.py}`

### Raw outcome (final corrected audit)

| Check | Result |
|-------|--------|
| Species parsed (foam / Chemkin) | 106 / 106 |
| max rel_cp (foam vs Cantera) | **3.0e-5** (h2) |
| max rel_hs | **3.0e-5** |
| max \|Δhs\| | ~1.7 kJ/kg on H/H2 (from 0.03% MW mismatch foam vs CT) |
| min cp | 847 J/kg/K (co2) — **no cp ≤ 0** |
| max cp discontinuity at Tcommon | 0.04 J/kg/K |
| max \|h_high−h_low\| at Tcommon | ~2 J/kg |
| Chemkin vs foam cp | **0** (bit-identical NASA sets) |
| Implausible Tcommon | `h` (5000, single-range), `c8h17coch2` (2042) — not defects |

False alarm during development: an early audit version evaluated `h(298)` with the high-T polynomial when T>Tcommon, manufacturing huge “hs errors.” Corrected before interpretation.

Also verified explicitly for H2: foam `lowCpCoeffs` / `highCpCoeffs` match Cantera `NasaPoly2` low/high (Cantera packs `[Tmid, high7, low7]` — easy to misread).

### Interpretation

- **H1 (corrupted / swapped / mangled NASA data in conversion) is DEAD.**
- Defect is **not** in YAML→Chemkin→foam coefficient transcription.
- Combined with E1: crash is **mechanism- or chemFoam-path-level**, not custom-solver-specific and not bad JANAF cards.

**Next:** E3 (alternate-mechanism control) to distinguish Luo-specific chemistry/stiffness vs case-level chemFoam settings.

---

## E3 — Alternate-mechanism control (53-sp Luo skeletal)

**Status:** COMPLETE  
**Date:** 2026-07-17  
**Mechanism:** PelePhysics `dodecane_lu_qss/skeletal.yaml` (53 sp / 268 rxn) via the same
YAML→Chemkin→`chemkinToFoam` pipeline into `validation/zeroD/e3_skeletal_dodecane/`.  
**IC:** MidT_MidP analogue (800 K, 10 atm, Z=0.062, fuel `NC12H26`).

### Thermo audit on converted skeletal

Majors clean to ~3e-5. A few large intermediates show ~0.1% cp error (`oc12h23ooh` 0.17%) —
not H1-class corruption. No cp≤0. Chemkin↔foam identical.

### chemFoam outcomes

| Solver | Result | Crash T | Wall |
|--------|--------|---------|------|
| stock `ode` | **ABORT** h→T Newton | ~1391 K | 18 s |
| custom `cvode` | **ABORT** same | ~1388 K | 15 s |
| custom `qss` | **ABORT** same | ~1388 K | 8 s |

### Extra controls

| Control | Result |
|---------|--------|
| ESI GRI chemFoam tutorial (stock, tutorial settings) | **Completes** to equilibrium (T≈2660 K, 758 steps, 27 s) |
| Luo MidT stock + GRI-like `odeCoeffs.relTol=0.1`, `maxDeltaT=1e-4` | **Still ABORT** (~1392 K) |

`thermophysicalProperties` matches GRI (hePsiThermo / reactingMixture / janaf / sensibleEnthalpy).

### Interpretation (matrix)

- Alternate **also crashes with stock** → not “Luo full-mechanism conversion only.”
- GRI tutorial **survives** → chemFoam itself is fine; failure is tied to **n-dodecane ignition runaway** (full + skeletal) under our MidT path, not a broken FoamFile header / thermoType.
- GRI-like tolerances do not rescue Luo → not simply “our ode tols too tight.”

**Hypothesis update:** H1 remains dead. Failure class = chemFoam outer enthalpy/Newton path under stiff n-dodecane thermal runaway (stock included).

---

## E4 — Crash-state autopsy (proxy Y from Cantera)

**Status:** COMPLETE (proxy — true OF Y dump still recommended)  
**Artifacts:** `validation/zeroD/e4_autopsy/{hs_vs_f.png,hs_contributors.png}`

Used Cantera MidT trajectory Y at first T≥1850 K as a stand-in for OF crash composition;
evaluated mixture `hs(T;Y)` with **foam** NASA coeffs; overlaid E1 FATAL target `f=1.67368e6`.

| Check | Result |
|-------|--------|
| Mixture hs(T) | **Monotone** (min ∂hs/∂T ≈ 1100 J/kg/K) |
| JANAF intersection | Tlow=300, Thigh=**3000** (ch3o) |
| hs at T_crash≈1850 | ~1.97e6 J/kg |
| chemFoam `f` | 1.67e6 J/kg (**~300–480 kJ/kg below** hs at ODE-like T) |
| T where hs=f | ~1638 K |
| Top contributors | n2, h2o, co, o2, co2 (all smooth) |

### Interpretation

- No kink/plateau from a single bad species → **reinforces H1 dead.**
- Target `f` is reachable on the Cantera-Y curve, but **lags** the physical sensible enthalpy at the reported crash temperature → points to **OF state/accounting at the crash step** (Y and/or `integratedHeat`), not a non-invertible thermo surface.
- Caveat: without OF’s actual Y vector, this is a proxy. In-OF dump at FatalError remains valuable.

---

## E5 — Invariant logging (Cantera mimic of chemFoam Hc path)

**Status:** COMPLETE (Python mimic; OF-side debug switch still recommended as standing diagnostic)  
**Artifacts:** `validation/zeroD/e5_invariants/{invariants_mimic.png,invariants_mimic.npz}`

Mimicked chemFoam: `Qdot = -Σ Hc_i RR_i` with `RR = ρ ΔY/Δt`, `h_target = h0 + ∫ Qdot/ρ dt`,
compared to `hs(T_ode, Y)` along a Cantera const-p MidT integration.

| Invariant | Result |
|-----------|--------|
| R2 = \|hs_ode − h_target\| | **≤ ~1 J/kg** through equilibrium (max at end) |
| R2 at ignition / T≈1850 | ~0.01 J/kg |
| min Y | ~−1e-11 (noise) |
| ΣY | 1 ± 1e-9 |

### Interpretation

- When RR exactly equals the Y change, **Hc-based `integratedHeat` is consistent** with sensible enthalpy.
- Therefore the crash is **not** explained by “Hc vs ha is always wrong.”
- Combined with E1/E4: something in **OF’s stiff update** (RR/YEqn/ρ/substep interaction, or Newton starting state) corrupts the (Y, h) pair even for stock `ode`.

---

## E6 — Step-size discriminator

**Status:** COMPLETE  
**Run:** stock `ode`, `deltaT = maxDeltaT = 1e-7`, MidT Luo, original JANAF ranges.

| Result | Value |
|--------|-------|
| exit | 134 ABORT |
| wall | 82 s |
| crash T | **~1851 K** (same phase as E1) |

### Interpretation

- **Crash persists** → naive H3 (“just force smaller Δt”) is **DEAD** as a fix.
- Does not rule out a more subtle accumulation/Newton issue, but eliminates “Δt=1e-6 is the root cause.”

---

## E7 — High-T reverse-rate parity

**Status:** DEFERRED  
Not required to close the crash hypothesis set after E1–E6 (H1 dead; rates not implicated as primary crash cause). Still useful later for the QSS 18%-early gap.

---

## Diagnosis (campaign conclusion)

### Confirmed

1. **Custom solvers are not the cause of the abort** (E1: stock `ode`/`seulex` identical failure mode).
2. **JANAF / conversion thermo data are not corrupted** (E2: foam≡Chemkin≡Cantera to ~3e-5; no cp≤0; no material discontinuities).
3. **Failure occurs for n-dodecane ignition (106 and 53 species) in chemFoam’s `h = h0+∫Qdot/ρ dt` → `thermo.correct()` Newton**, while the ESI GRI tutorial completes (E3).
4. **Smaller CFD Δt does not fix it** (E6).
5. **Hc-based enthalpy accounting is thermodynamically consistent when ΔY is exact** (E5 Cantera mimic).

### Single root-cause statement

> **Root cause class:** chemFoam’s outer-loop enthalpy reconstruction + h→T Newton fails during the thermal runaway of n-dodecane (const-p MidT), independent of custom chemistry solvers and independent of JANAF coefficient fidelity. The stock ESI chemistry path updates `RR`/`Qdot(Hc)` and then re-inverts temperature from sensible enthalpy; under this stiff ignition that (Y, h) pair becomes non-convergent for OpenFOAM’s Newton even though per-species `hs_i(T)` are healthy and a Cantera-faithful Hc accounting stays consistent.

This is **H3 in a refined form** (chemFoam path fragility under stiff heavy-fuel runaway), **not** H1/H2/H4 as originally posed.

### What is *not* yet pinned (next instrumentation, not a silent fix)

- Exact OF `Y[]` and `integratedHeat` at the failing Newton step (true in-OF E4 dump).
- Whether `YEqn`/`rho`/`deltaTChem` substepping produces RR that disagrees with the Y change chemFoam applies (in-OF E5).

### Fix direction (only after that dump — do not clip T/h)

Per protocol: treat as chemFoam coupling for 0D validation — preferred options to evaluate with evidence:
- **(A)** Trust chemistry-solver T for 0D and bypass/rebuild `hEqn` for validation builds, or  
- **(B)** Reconstruct `h` from Σ Y_i hs_i(T_ode) after chemistry instead of `∫Qdot`, or  
- **(C)** Fix RR/Y/ρ consistency if in-OF E5 shows ΣRR or R2 exploding.

Do **not** raise Newton maxIter / clip T / switch mechanism for production.

### Definition-of-done status

| Item | Status |
|------|--------|
| Named root cause + experiment trail in this file | **Yes** (refined H3 / chemFoam path) |
| MidT to equilibrium stock+cvode+qss, original JANAF, no warnings | **Open** (fix not applied this campaign) |
| OF-CVODE ign within 1%; QSS gap re-measured | **Open** (pre-crash CVODE was ~1%; QSS ~18% parked) |
| E5 invariant logging behind debug switch in OF | **Open** (Python mimic done; OF switch TBD) |

**Git commits:** skipped — workspace is not a git repository.


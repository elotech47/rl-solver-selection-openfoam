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

## E8 — True in-OF state dump (COMPLETE)

**Status:** COMPLETE — **H5 (negative-Y / ΣY≪1) FALSIFIED.** Mechanism pinned to OF `cellMixture` JANAF-coeff blending.

**Date:** 2026-07-17  
**Solver:** local `applications/solvers/chemFoam` → `chemFoamDebug`  
**Switch:** `OFRL_DEBUG_STATE=1` (off path bit-identical to stock `chemFoam.out`)

### Newton form (confirmed from `thermoI.H`)

```
Tnew = limit( Test - (F(p,Test) - f) / dFdT(p,Test) )
```
i.e. `T_new = T_old − (hs_mix(T_old) − f) / cp_mix(T_old)` on the **blended** `cellMixture` thermo.

### Instrumentation (before `thermo.correct()`)

Per step to `e8_state.csv`: ΣY, minY (+5 most-neg), `hsSum/cpSum` (= Σ Yi·Hs_i), `hsCell/cpCell` (= `cellMixture` blend), f, rho triplet, Qdot increment.  
Crash dumps: `e8_crash_state.dat`, `e8_crash_hs_cp.dat` (both hsSum and hsCell vs T).

### Bit-identical check (switch off)

```bash
# stock chemFoam vs chemFoamDebug with OFRL_DEBUG_STATE unset
diff e8_state/bitidentical/stock/chemFoam.out \
     e8_state/bitidentical/debug_off/chemFoam.out
# → empty (BIT_IDENTICAL_PASS)
```

### Raw outcome — stock `ode` MidT (Δt=1e-6)

| Quantity | Result |
|----------|--------|
| ΣY | **1.0 exactly** every step |
| min Y | ≥ 0 (worst −1e−41 noise); crash Y: **0 negatives**, ΣY=1 |
| rho triplet | \|ρ_thermo−ρ_chem\| = **0**, \|ρ_fromC−ρ_chem\| = **0** |
| Ignition T≥1200 | t ≈ 2.149e−3 s |
| Abort | same Newton FATAL ~1852 K |

**Late dump (t≈2.27257e−3, Tprev=1811 K, f=1.669e6):**

| | hs | cp |
|--|----|----|
| Σ Yi·Hs_i / Cp_i (`hsSum`/`cpSum`) | 1.920e6 | **1407** (physical) |
| `cellMixture` blend (`hsCell`/`cpCell`) | 1.669e6 ≈ f | **201** (collapsing) |

`hs(T)` / `cp(T)` on the **blended** surface at crash Y:

| T [K] | hsSum | cpSum | hsCell | cpCell |
|------:|------:|------:|-------:|-------:|
| 800 | 5.76e5 | 1216 | 5.76e5 | 1216 |
| 1638 | 1.68e6 | 1386 | 1.58e6 | 796 |
| 1841 | 1.96e6 | 1410 | 1.67e6 | **64** |
| 2200 | 2.47e6 | 1441 | 1.27e6 | **−2658** |
| 2600 | 3.06e6 | 1465 | −9.2e5 | **−9062** |

Hand Newton on **cellMixture** at late dump: `R2cell≈100 J/kg`, `TnewProbe≈1812` (ill-conditioned; cpCell→0).  
Stock FATAL last iterate stays near 1841–1851 with tiny steps — consistent with cpCell→O(10) then sign-flip (cpCell_min≈12 at abort).

Custom `cvode` (same instrumentation): FATAL `T0=1814 → new T:2200`, `f=1.732e6`; dump shows `cpCell≈190`, `hsCell` vs f drives `TnewProbe≈2142` — **reproduces the preamble-style large Newton jump** once cpCell is small/wrong. Y still healthy (ΣY=1, minY=0).

Artifacts: `validation/zeroD/e8_state/{stock_ode,cvode,bitidentical}/`, plots `e8_overview.png`, `e8_hs_vs_f.png`.

### Interpretation (E8 table)

| Observation | Conclusion |
|-------------|------------|
| min Y ramps to −1e−3; rho agrees | **Not observed** — H5 dead |
| rho triplet disagrees | **Not observed** |
| Y healthy but hs(Tprev,Y)≪physical | Partially: **ΣYi·Hs is physical**; the quantity Newton uses (`hsCell`) tracks f while **cpCell collapses** |
| Everything healthy & f reachable on ΣYi·Hs | Yes for mass-weighted sum — but **not** on `cellMixture`; escalate was unnecessary once hsCell/cpCell logged |

**E8b:** skipped (no negative-Y ramp).

### Hypothesis update

- **H5 dead.** Corruption is not RR→YEqn negative mass fractions.
- **New H6 (named):** ESI `multiComponentMixture::cellMixture` blends JANAF NASA coefficients by Y, then evaluates Hs/Cp on that single pseudo-species. For Luo burnt-gas Y during runaway, **cpCell→0 and goes negative** while Σ Yi·Cp_i stays ~1400 J/(kg·K). `thermo.correct()` / `mixture.THE` uses the blended surface → Newton fails. GRI (below) has hsSum≡hsCell and healthy cpCell throughout.

---

## E10 — Last-species / normalization audit (COMPLETE, reading only)

### chemFoam `YEqn.H` (v2312, verbatim behavior)

```cpp
forAll(Y, specieI)
{
    volScalarField& Yi = Y[specieI];
    solve(fvm::ddt(rho, Yi) - chemistry.RR(specieI), "Yi");
}
```

- **No** ΣY normalization  
- **No** residual `1−ΣY` assigned to a last/inert slot  
- **No** `Y.max(0)` / `clamp_min`  

`createFields.H`: no inertIndex handling.

### reactingFoam `YEqn.H` (for later 2D reference)

Solves all species **except** `inertIndex`; `Yi.clamp_min(0)`; then `Y[inertIndex] = 1 - Yt` with `clamp_min(0)`.

### Last species in mechanisms

| Mechanism | n | first | last | N2 index |
|-----------|---|-------|------|----------|
| Luo foam (106) | 106 | `h` | **`c8h15`** | 6 (early) |
| E3 skeletal 53 | 53 | `NC12H26` | **`N2`** | last |
| GRI tutorial foam | 53 | `CH4` | **`CH3CHO`** | 47 (not last) |

**E10 step 3 (reorder):** **not executed** — chemFoam has no residual/last-slot treatment; speculative reorder forbidden.

---

## E9 — const-p vs const-v 2×2 (COMPLETE)

### `constantProperty` records

| Case | `constantProperty` |
|------|--------------------|
| This MidT Luo case | **pressure** |
| ESI GRI chemFoam tutorial | **pressure** (not volume — E3 “tutorial path” was already const-p) |

### 2×2 results (stock `ode`, `OFRL_DEBUG_STATE=1`)

| Case | Energy path | Outcome |
|------|-------------|---------|
| GRI, Δt=maxΔt=1e−6, endTime=0.07 | const-**p** | **SURVIVES** → Teq≈2660 K (70016 steps, wall≈650 s) |
| GRI, same numerics | const-**v** | **SURVIVES** → Teq≈2941 K (70074 steps, wall≈1552 s) |
| Luo MidT | const-**v** | **ABORT** ~1823 K (same blended-cp failure; wall≈69 s) |
| Luo MidT | const-**p** | **ABORT** ~1852 K (= E8; wall≈64 s) |

GRI diagnostics: `max|hsSum−hsCell|=0`, `cpCell_min≈1341` (healthy) on both energy paths.  
Luo: `max|hsSum−hsCell|≈3.0e5 J/kg`, `cpCell_min≈12` at abort — **both** const-p and const-v.

### Attribution

> **dodecane@const-v fails too** → energy-path attribution collapses. Failure is **not** specific to const-p `hEqn`. Matches E8: blended JANAF `cellMixture` pathology under Luo burnt-gas Y, independent of whether f comes from `h0+∫Q` or `u0+p/ρ+∫Q`.

E3’s “GRI works ⇒ fuel-specific” stands, but **not** because GRI used a different energy path — both are const-p capable; GRI’s blended thermo remains well-behaved.

Artifacts: `validation/zeroD/e9_constprop/`.

---

## Diagnosis (updated after E8–E10)

### Confirmed (E1–E10)

1. Custom solvers exonerated (E1).  
2. Per-species JANAF data clean (E2).  
3. n-dodecane fails; GRI survives (E3/E9) — **both** energy paths.  
4. Δt↓ does not fix (E6).  
5. Hc accounting OK when ΔY exact (E5).  
6. **Y/ρ healthy at crash; H5 dead (E8).**  
7. **No chemFoam last-slot / clip (E10).**  
8. **Smoking gun (E8):** `cellMixture` blended cp collapses / goes negative for Luo runaway Y; ΣYi·Cp stays physical; Newton uses the blended surface.

### Root-cause statement

> **Root cause (H6):** OpenFOAM’s `multiComponentMixture::cellMixture` builds a pseudo-species by Y-weighted blending of each species’ NASA-7 *coefficient arrays* (`janafThermo::operator+=`). The mixture inherits **Tcommon from species[0]** (equality of Tcommons is only FATAL when `janafThermo::debug` is on). Property evaluation then switches low/high on that single Tcommon_mix. The blend equals the physical mass-weighted average `Σ Yi·cp_i` **iff all species share the same breakpoints**. Luo n-dodecane foam thermo has **28 distinct Tcommons**; species[0]=`h` has Tcommon=**5000 K**, so through the 1700–1850 K crash band the Newton always sees blended *low*-range coeffs while `Σ Yi·cp_i` correctly uses each species’ own range — burnt-gas `cpCell` collapses / goes negative (E10b severity: **−151% at 2000 K**, −681% at 2600 K) while `cpSum` stays ~1400 J/(kg·K). GRI MidT survives because it is near-uniform (50/53 at Tcommon=1000; species[0]=CH4 aligned) and burnt blend error is ~0%. `hePsiThermo::correct()` / `THE` inverts T on the blended surface → Newton FATAL. Solvers only supply (Y, Qdot). **Fix (Option R):** harmonized-Tcommon refit [300, 1000, 3500] restores blend identity to round-off; stock THE ships.

---

## FIX — mass-weighted h→T in local chemFoam (APPLIED)

**Date:** 2026-07-17  
**Scope:** `applications/solvers/chemFoam/massWeightedT.H` included from `hEqn.H` (local `chemFoamDebug` build only; installed ESI tree untouched).

### What changed

After `h[0] = h0 + integratedHeat` (or const-v equivalent):

1. **Newton on Σ Yi·Hs_i(T) = f** using per-species `composition.Hs/Cp` (same basis as `h0` in `readInitialConditions.H`).
2. Set `he` to blended `Hs(T_new)` so stock `thermo.correct()` THE is a numerical no-op, then call `correct()` to refresh `psi` (ρ = p·ψ).
3. Restore `he = f` for bookkeeping.

No Y/T clipping, no Newton maxIter change, no bypass of chemistry or `∫Qdot/ρ`.

### Verification — MidT_MidP, original JANAF, Δt=maxΔt=1e−6, endTime=0.0035

| Solver | Outcome | τ_ign (T≥1200) | T_end [K] | vs handoff τ_ign |
|--------|---------|----------------|-----------|------------------|
| stock `ode` | **End** (32745 steps, ~91 s) | 2.151 ms | 2601 | — |
| custom `cvode` | **End** (3522 steps, ~21 s) | 2.144 ms | 2609 | **0.56%** (PASS ≤1%) |
| custom `qss` | **End** (3523 steps, ~5 s) | 1.949 ms | 2631 | **15.7% early** (FAIL — E7 parked) |

Artifacts: `validation/zeroD/fix_verify/{ode,cvode,qss}/`.

No warnings in solver logs. E8 `OFRL_DEBUG_STATE` instrumentation unchanged.

### 2D note

reactingFoam still uses `cellMixture` THE for energy; this chemFoam fix is the 0D validation path. A reactionThermo-level fix (or reactingFoam patch) is still required before coflow/opposedJet.

### Definition-of-done status

| Item | Status |
|------|--------|
| Named mechanism + experiment trail | **Yes — H6** |
| MidT to eq stock+cvode+qss, original JANAF | **Yes** (chemFoamDebug) |
| OF-CVODE ign within 1% | **Yes** (0.56%) |
| QSS gap re-measured (E7) | **Open** (~16% early, unchanged class) |
| E8 instrumentation behind debug switch | **Done** |

**Git:** commits on `main` through E8–E10 + fix.

---

## E10b — Tcommon histogram (COMPLETE; human gate before E11)

**Date:** 2026-07-17  
**Claim under test:** coefficient blend ≡ property average iff shared breakpoints; GRI works because (near-)uniform; Luo fails because heterogeneous.

### Method

Script `validation/thermo_audit/e10b_tcommon_hist.py` parses foam `thermo` with brace-aware extraction of `(Tlow, Tcommon, Thigh)` per species for Luo 106, skeletal 53 foam, and ESI GRI tutorial.

### Results

| Mechanism | n_sp | distinct tuples | distinct Tcommon | dominant Tcommon |
|-----------|------|-----------------|------------------|------------------|
| Luo 106 | 106 | **31** | **28** | 1000 K on **22/106** only |
| skeletal foam | 52 | 8 | 5 | 1000 K on 35/52 |
| GRI tutorial | 53 | 8 | **4** | 1000 K on **50/53** |

GRI outliers (Tcommon ≠ 1000): **HOCN** (1368), **HCNO** (1382), **HNCO** (1478). Thigh also varies widely on both GRI and Luo.

Artifacts: `validation/thermo_audit/e10b_tcommon/{SUMMARY.md,summary.json,*_species.json}`.

### Thesis-ready root-cause paragraph

> OpenFOAM evaluates mixture sensible enthalpy and heat capacity for `hePsiThermo::correct()` / `THE` by blending each species' NASA-7 *coefficient arrays* by mass fraction (`multiComponentMixture::cellMixture`) and then evaluating the resulting pseudo-species polynomials. That blend is algebraically identical to a mass-weighted property average (`Σ Yi·cp_i`, `Σ Yi·hs_i`) *only* when every species shares the same temperature breakpoints (especially a shared `Tcommon`). In the ESI GRI chemFoam tutorial thermo, **50/53** species share Tcommon = 1000 K (near-uniform; outliers: HOCN, HCNO, HNCO with Tcommon ∈ {1368, 1382, 1478}; Thigh also varies → 8 distinct full tuples). The Luo n-dodecane foam thermo has **31** distinct (Tlow,Tcommon,Thigh) tuples and **28** distinct Tcommon values across 106 species; the skeletal foam thermo shows **8** distinct tuples and **5** distinct Tcommon (52 species parsed). Above the lowest Tcommon in a mixed cell, some species are already on their high-range coefficients while others remain on low-range ones, so the blended coefficients no longer represent any physical mixture average: burnt-gas blended cp collapses toward zero and can change sign, while `Σ Yi·cp_i` stays O(1400) J/(kg·K). The h→T Newton then diverges (E8). This is **H6**: a representation defect exposed by OpenFOAM's coefficient blend under mechanism-heterogeneous JANAF breakpoints, not a corruption of per-species thermo tables (E2).

### Claim check / stop

- Luo heterogeneous: **PASS** (not uniform → E11 refit premise not void).
- GRI exact-uniform: **FAIL**; GRI near-uniform (campaign “or near”): **PASS** (50/53).
- Campaign stop condition *“E10b contradicts the uniformity claim”*: **soft hit** — exact GRI uniformity was overstated; severity still Luo ≫ GRI (28 vs 4 Tcommons; 22/106 vs 50/53 at 1000 K). Why GRI MidT still shows `hsSum≡hsCell`: the three N-outliers are typically trace in CH4/air, so the blend remains dominated by shared-breakpoint species.

**Action:** do **not** start E11 until human acknowledges this nuance and green-lights Option R work.

---

## E10b add-on — weighted severity (COMPLETE; claim-check CLOSED)

**Date:** 2026-07-17  
**Human ack:** proceed Option R + severity table + dual-Tc refit directives.

### Method

`validation/thermo_audit/e10b_severity.py` — Cantera HP-equilibrium burnt Y (Luo MidT moles; GRI tutorial CH4/air); OpenFOAM `janafThermo` blend replica (Tcommon_mix = species[0] Tcommon; Y-weighted low/high mass-basis coeffs).

### Severity table (blended cp vs Σ Yi·cpᵢ)

| Mech | species[0] / Tcommon_mix | T=1200 | T=1600 | T=2000 | T=2400 | T=2600 | worst |
|------|--------------------------|--------|--------|--------|--------|--------|-------|
| Luo | `h` / **5000 K** | −1.9% | −33% | **−151%** | −439% | −681% | 681% @2600 |
| GRI | `CH4` / 1000 K | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | ~0 |

Artifacts: `validation/thermo_audit/e10b_tcommon/{severity.json,SUMMARY.md}`.

### Interpretation

GRI survives because the blend identity holds at burnt Y (near-uniform Tcommon + species[0] aligned). Luo collapses because species[0]=`h` forces Tcommon_mix=5000 K → mixture always evaluates blended *low* coeffs through the 1700–1850 K crash band; Luo `oh` Tcommon=1710 K sits in that band. **Claim-check status: CLOSED.**

---

## E11.1 — Harmonized-Tcommon refit (COMPLETE; quality gate SOFT-FAIL)

**Date:** 2026-07-17  
**Script:** `mechanisms/refit/refit_tcommon.py`  
**Window:** shared **[300, Tc, 3500]**; trade Tc ∈ {1000, 1400}; select by worst-species max|Δcp|/cp.

### Trade study

| Tc | worst species | max\|Δcp\|/cp | max\|Δhs\| [kJ/kg] | fails |
|---:|---------------|---------------:|-------------------:|------:|
| **1000** ← selected | c8h17coch2 | **0.430%** | 3.66 | **4/106** |
| 1400 | ch4 | 0.686% | 3.44 | 13/106 |

**Gate failures at Tc=1000** (campaign gate: ≤0.2% cp, ≤2 kJ/kg hs):
- `c8h17coch2` (orig Tcommon=2042): 0.430% cp, 3.66 kJ/kg hs
- `c3h4-a` (1400): 0.305% cp, 2.59 kJ/kg hs
- `oh` (1710): 0.262% cp (hs OK)
- `c2h6` (1384): cp OK (0.193%), hs 2.15 kJ/kg

`ch3o` Thigh=3000→3500: documented high-poly extrapolation; passed gates.  
`h` single-range cp=5/2·R: both polys identical @ machine precision.

**Artifacts:** `mechanisms/refit/{n-dodecane_refit.yaml,E11_1_SUMMARY.md,trade_study.json,chemkin/,foam/}`  
Foam breakpoints: **106/106** at (300, 1000, 3500).

### Blend-identity check on refit foam (bonus)

Burnt MidT Y, OF blend vs ΣYi·cp: **0.0000%** at T∈{1200…2600} (was −681% on original). Direct confirmation of E10b claim under uniform Tcommon.

### Stop / human decision

E11.1 **strict quality gates not met** (4 species). Campaign stop: choose **R-with-relaxed-gate** vs **Option P**. E11.2 kinetic evidence below still collected for the decision package. **E11.3 stock OF MidT deferred until gate call.**

---

## E11.1 add-ons + Option R decision (COMPLETE)

**Date:** 2026-07-17  
**Decision:** **Option R ships** with relaxed fidelity gates (0.5% cp / 4 kJ/kg).

### Add-on (1) Equilibrium invariance — PASS
max\|ΔT_equil\|=**0.0079 K**, max\|ΔY_major\|=**2.9e-7** on Z∈[0.02,0.12]×p∈{10,30,60}.

### Add-on (2) Effect-size of 4 strict-gate misses — PASS
Worst mixture-relative contribution: **oh** 1.1e-5 ≪ 1e-4. See `mechanisms/refit/e11_1_addons/` and `DECISIONS.md`.

---

## E11.3 — Stock THE MidT on refit thermo (COMPLETE; GREEN)

**Config:** case `chemFoam_0D` with refit foam; `OFRL_STOCK_THE` path = stock `thermo.correct()` (no massWeighted).

| Run | App | Outcome | τ_ign | T_end | vs Cantera-refit |
|-----|-----|---------|------:|------:|------------------|
| stock ode | ESI `chemFoam` | **End** (92 s) | 2.151 ms | 2601.1 K | — |
| custom cvode | `chemFoamDebug` + stock THE | **End** (20 s) | 2.144 ms | 2608.8 K | **−0.65%** (PASS ≤1%) |

Cantera-refit MidT: τ_ign=2.158 ms, T_eq≈2601 K.

### Blend-vs-ΣYi·cp along trajectory
Pre-ignition: **exact 0**. Post-ignition max \|cpCell−cpSum\|/cpSum ≈ **0.10%** — tracks ΣY≈1.001 chemistry drift (cpCell uses Y-normalized blend), **not** H6 collapse. When ΣY=1, identity holds (Python burnt check 0.0000%). No Newton FATAL, no JANAF warnings.

### Production config
- `mechanisms/foam/{thermo,reactions}` ← refit [300,1000,3500]
- Original heterogeneous archived: `mechanisms/foam_original_heterogeneous/`
- `massWeighted*.H` retired to `diagnostics/h6_massWeighted/`
- chemFoam / reactingFoam `hEqn`/`EEqn` use stock `thermo.correct()`

Artifacts: `validation/zeroD/e11_3/{stock_ode,cvode_stockTHE,summary.json}`.

---

## E11.2 — Kinetic invariance (COMPLETE; PASS)

Cantera original vs refit YAML:

| Gate | Result |
|------|--------|
| \|Δτ_ign\| ≤ 0.5% on T0∈{750,800,1000}×p∈{10,30,60} atm | **PASS** — max **0.016%** |
| Spot rates/Kc (50 states, 800–2800 K) | max \|Δkf\|=0, \|Δkr\|=0.12%, \|ΔKc\|=0.50% |

Artifacts: `mechanisms/refit/e11_2_kinetic/`.


---

## E13 — QSS parity on Option R (COMPLETE; RED)

**Date:** 2026-07-18  
**Report:** `validation/zeroD/e13_qss/E13_FINAL.md`

| Gate | Result |
|------|--------|
| E13.1 pins OF vs CVODE | MOSTLY PASS (T2001 +4%) |
| E13.2 OF rates ≤0.1% | FAIL (char 0.23–0.35%) |
| MidT OF-QSS vs Py-QSS | **FAIL −19% early** |
| Teq OF-QSS − OF-CVODE | **FAIL +39 K** |
| MidT OF-CVODE vs Py-CVODE | PASS (−1.1%) |

**Stop:** outer chemFoam/QSS path defect; no unilateral fix. 2D QSS production remains blocked.

## E14 — Energy ledger (Campaign 4) — ESCALATE

**Date:** 2026-07-19  
**Report:** `validation/zeroD/e14_ledger/E14_REPORT.md`

| Gate | Result |
|------|--------|
| E14.2 ΔY / Qdot ledger | PASS |
| E14.3 ha/cp vs NASA/Cantera | PASS (~1e-7) |
| Teq(QSS)−Teq(CVODE) ≤2 K | **FAIL +40.3 K** |

**Stop:** accounting and thermo-range consistent; Teq offset unexplained → escalate (no QSS algorithm change). E15.2+ and 2D QSS remain blocked.

---

## E15 — CONFORM close-out (COMPLETE; 2D QSS UNBLOCKED)

**Date:** 2026-07-19  
**Decision:** Production OF-QSS = corrector **T-freeze** (`epsmin=0.02`). Advisor CONFORM 2026-07-19.

| Item | Result |
|------|--------|
| E15.2b T-freeze | NTC + timeouts PASS; MidT ΔTeq residual noted |
| 38-condition T-freeze map | **38/38 QSS ok**; timeouts cleared; ΔTeq sign match vs Py **15→29** |
| Equilibration audit (800/10/1.5, 1000/10/0.5) | Both **settled**; anomalies **real — no fix** |
| CVODE 1000/1 holes | Rerun wall_cap=3600 (fill ΔTeq) |
| Frozen baseline | **`validation-baseline-v1`** (`823b1c2`; alias `e15-conform-baseline-v1`) + `FROZEN_VALIDATION_BASELINE_v1.md` + `FROZEN_RUNG_BC_ACCEPTANCE.md` |

**2D QSS production: UNBLOCKED.** Proceed to opposed-jet `qssOnly` + `rlAdaptive` smoke per master spec §5.2. Prior E13/E14 “2D QSS blocked” stop conditions are superseded by this conform close-out.

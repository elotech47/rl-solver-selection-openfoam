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

## Diagnosis (updated after E8–E10) — STOP for human

### Confirmed (E1–E10)

1. Custom solvers exonerated (E1).  
2. Per-species JANAF data clean (E2).  
3. n-dodecane fails; GRI survives (E3/E9) — **both** energy paths.  
4. Δt↓ does not fix (E6).  
5. Hc accounting OK when ΔY exact (E5).  
6. **Y/ρ healthy at crash; H5 dead (E8).**  
7. **No chemFoam last-slot / clip (E10).**  
8. **Smoking gun (E8):** `cellMixture` blended cp collapses / goes negative for Luo runaway Y; ΣYi·Cp stays physical; Newton uses the blended surface.

### Root-cause statement (replace prior H3 location-only claim)

> **Root cause:** During Luo n-dodecane thermal runaway, OpenFOAM’s mass-fraction blend of JANAF coefficients (`multiComponentMixture::cellMixture`) produces a pseudo-species whose `Cp(T)` collapses toward zero and becomes negative above ~2000 K, while the physically correct mixture `Σ Yi Cp_i(T)` remains ~1400 J/(kg·K). `hePsiThermo::correct()` inverts T with `mixture.THE(h,p,T)` on that blended surface, so the h→T Newton fails (ill-conditioned then oscillatory). Stock and custom chemistry solvers only supply (Y, Qdot); they are not the defect. GRI’s blend stays faithful (`hsSum≡hsCell`), so the tutorial survives.

### Fix conversation (do **not** apply yet — awaiting human)

Options to discuss (none implemented):
- Evaluate mixture Hs/Cp as **Σ Yi·Hs_i** for THE (or equivalent) instead of NASA-coeff blending, at least for chemFoam / validation.  
- Or restrict blending / switch temperature handling for mechanisms with disparate `Tcommon` / Thigh.  
- reactingFoam still uses the same `cellMixture` for energy — 2D will hit this unless addressed.  
- Prior (A)/(B) bypasses remain **on hold** (would mask without fixing blend).

### Definition-of-done status

| Item | Status |
|------|--------|
| Named mechanism + experiment trail | **Yes — H6 cellMixture JANAF blend / cp collapse** |
| MidT to eq stock+cvode+qss, original JANAF | **Open** (fix not applied) |
| OF-CVODE ign within 1%; QSS gap (E7) | **Open** (after fix) |
| E8 instrumentation behind debug switch | **Done** (`OFRL_DEBUG_STATE`) |

**Git:** repo initialized; commits per experiment on `main`.


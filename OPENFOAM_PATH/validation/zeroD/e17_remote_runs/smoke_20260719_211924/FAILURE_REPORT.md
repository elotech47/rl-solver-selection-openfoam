# E17 Failure Report: Post-Ignition Blow-Up of QSS / RL-Adaptive Chemistry

**Campaign ID:** `smoke_20260719_211924`  
**Date:** 2026-07-19 / 2026-07-20  
**Case:** OpenFOAM `reactingFoam` opposed-jet 2D (`cases/opposedJet_2D`)  
**Purpose of this note:** Give an external expert enough context to diagnose whether the failure is in the QSS integrator, thermo/species coupling, RL policy, or CFD settings.

---

## 1. Executive summary

A three-mode chemistry smoke on a small 2D opposed-jet mesh shows a clear split:

| Mode | Result | Wall time | Latest CFD time |
|------|--------|----------:|----------------:|
| **cvodeOnly** (`method rl`, force CVODE) | **Success** to `endTime` | ~20 253 s (~5.6 h) | 5×10⁻⁴ s |
| **qssOnly** | **SIGFPE** shortly after ignition | ~83 s | ~1.0415×10⁻⁴ s |
| **rlAdaptive** | **SIGFPE** on the same post-ignition path | ~221 s | ~1.0306×10⁻⁴ s |

**Working interpretation:** The failure is **not primarily an RL-runtime bug**. Pure CVODE through the same `rlChemistryModel` path is stable through ignition and to end time. Both `qssOnly` and `rlAdaptive` ignite, then temperature hits the solver clip (**3500 K**), `cp` becomes pathological, and MPI ranks die with **SIGFPE (signal 8, exit 136)** under OpenFOAM’s `FOAM_SIGFPE`.

In `rlAdaptive`, the TorchScript policy switched the whole mesh to **QSS** well before ignition and kept **~99 % QSS** into the blow-up (including **all cells with T > 2000 K** at the last logged decision). So RL behaved like near-pure QSS at the critical moment and inherited the QSS failure.

---

## 2. Configuration snapshot

### 2.1 CFD / case

- Solver: `reactingFoamDebug` (OpenFOAM **v2312**), Docker amd64, **16 MPI ranks**
- Mesh: opposed-jet 2D, **3200 cells**
- `endTime = 5e-4`, `deltaT = 1e-5`, `adjustTimeStep yes`, `maxCo = 0.4`
- Thermo: `psiReactionThermo`, JANAF / perfect gas / Sutherland, sensible enthalpy
- Hot-kernel IC (Cantera-built): `Z=0.05`, `T_kernel=1300 K`, `p=10 atm`, `Y_nc12h26=0.05`, balance O₂/N₂  
  (air BC ~1350 K; ignition scout previously reached ~2800 K with CVODE)

### 2.2 Chemistry (`constant/chemistryProperties`)

```
chemistryType { solver ode; method rl; }
rl {
    mode                <cvodeOnly | qssOnly | rlAdaptive>;
    maxChemDeltaT       1e-6;
    dtRef               1e-6;
    numSteps            20;          // τ_dec = dtRef * numSteps = 2e-5
    confidenceThreshold 0.6;
    manifest            "/work/policy/policy_manifest";
    torchScript         "/work/policy/policy.ts";
}
qssCoeffs {
    epsmin 0.02; epsmax 100;
    dtmin 1e-12; dtmax 1e-06;
    abstol 1e-11; itermax 2;
    Tfreeze true;
}
cvodeCoeffs {
    relTol 1e-08; absTol 1e-12; maxSteps 100000;
}
```

Shared libraries: `libqssChemistrySolver`, `libcvodeChemistrySolver` (SUNDIALS CVODE 6), `libpolicyRuntime`, `librlChemistryModel`.

**Note:** All three modes use `method rl` so that `solverFlag` / `chemCpuTime` instrumentation is comparable; mode switches force CVODE-only, QSS-only, or policy selection.

### 2.3 RL decision semantics

- Flag **0 = CVODE**, **1 = QSS**
- Decisions held for `τ_dec = 2×10⁻⁵` s of chemistry time
- Per-cell CSV columns: `time, chemTime, celli, flag, conf, p, T, P, Y0..Y7, …`
- In parallel, CSV is written under **`processorN/rl_decisions.csv`** (not case root)

---

## 3. Evidence by mode

### 3.1 cvodeOnly — reference success

- Completed to `t = 5×10⁻⁴` without FATAL / SIGFPE.
- Peak temperatures in the flame are physical (~2780–2824 K), not clipped at 3500 K.
- Example reconstructed field extrema (`fields_ascii`):

| t [s] | Tmin [K] | Tmax [K] |
|------:|---------:|---------:|
| 2×10⁻⁴ | 918 | 2824 |
| 3×10⁻⁴ | 853 | 2789 |
| 5×10⁻⁴ | 783 | 2786 |

This establishes that the **mesh, IC/BC, mechanism linkage, and CVODE path inside `rlChemistryModel` are viable** for this case.

### 3.2 qssOnly — post-ignition thermo blow-up → linear-solver FPE

Ignition proceeds normally until ~1.03×10⁻⁴ s, then:

| CFD time [s] | Tmax [K] | cp max (propSanity) | Notes |
|-------------:|---------:|--------------------:|-------|
| 1.000×10⁻⁴ | 2162 | ~1824 | heating |
| 1.029×10⁻⁴ | 2709 | ~1836 | near peak flame T |
| 1.037×10⁻⁴ | 2747 | **3590** | internal Tmin collapses to 300 K in propSanity |
| 1.038×10⁻⁴ | **3500** | ~4953 | **T clip hit** |
| 1.041×10⁻⁴ | 3500 | **~12105** | cp runaway |
| 1.0415×10⁻⁴ | — | — | **SIGFPE** |

**Crash site (qssOnly):** during PIMPLE, after solving enthalpy, in **`Foam::PBiCGStab::scalarSolve`** / `sumProd` — typical of NaN/Inf entering a species (or related) transport solve once thermo is corrupted. Exit **136**.

So for pure QSS the proximate crash is in the **flow solver**, after chemistry/thermo have already become non-physical.

### 3.3 rlAdaptive — same thermo path; crash inside CVODE RHS

Timeline mirrors qssOnly (slightly different Δt schedule):

| CFD time [s] | Tmax [K] | cp max | Notes |
|-------------:|---------:|-------:|-------|
| 1.000×10⁻⁴ | 2226 | ~1822 | |
| 1.013×10⁻⁴ | 2709 | ~1830 | |
| 1.026×10⁻⁴ | 2768 | **3603** | same “cp jump + Tmin→300” signature |
| 1.029×10⁻⁴ | **3500** | ~4968 | clip |
| 1.030×10⁻⁴ | 3500 | ~4467–5837 | |
| 1.0306×10⁻⁴ | — | — | **SIGFPE** |

**CVODE error immediately before crash:**

```
[CVODE ERROR] CVode
  At t = 0 and h = 3.95086e-78, the corrector convergence test failed
  repeatedly or with |h| = hmin.
```

**Crash site (rlAdaptive):** SIGFPE while CVODE builds a dense DQ Jacobian:

`CVode` → `cvLsDenseDQJac` → `ofRlChem::cvodeRhsRl` → `StandardChemistryModel::omega`  
(also seen in `N_VWrmsNorm` on other ranks).

So after the composition/T state is already bad, **some cells request CVODE** (or CVODE is entered on a poisoned state) and the RHS / Jacobian evaluation FPEs under `FOAM_SIGFPE`.

---

## 4. RL usage (why adaptive did not “save” the run)

Merged from 16 ranks: `rlAdaptive/rl_decisions.csv` (19 200 rows).

| Aggregate | Count | Fraction |
|-----------|------:|---------:|
| CVODE (0) | 6437 | 33.5 % |
| QSS (1) | 12763 | 66.5 % |
| Mean confidence | — | ~0.88 |
| Near-0.5 “OOD” \|p−0.5\| < 0.1 | — | ~0 |

**Per decision epoch (all 3200 cells):**

| CFD time [s] | CVODE | QSS | Comment |
|-------------:|------:|----:|---------|
| 1×10⁻⁵, 3×10⁻⁵ | 3200 | 0 | early / pre-switch |
| 5×10⁻⁵ … 8.3×10⁻⁵ | 0 | 3200 | **mesh-wide QSS** |
| 1.00769×10⁻⁴ (last logged) | 37 | 3163 | **99 % QSS at ignition** |

At that last epoch:

- T range ≈ 892–2508 K  
- **All 2662 cells with T > 2000 K had flag = QSS**, with high `p_QSS` / conf (~0.95)

Field dumps of `solverFlag` look like `uniform 0` then `uniform 1` because OpenFOAM compresses identical cell values — **not an empty field**.

**Implication for the expert:** The policy is confident and QSS-preferring in the hot region. Either (a) that preference is wrong for this 2D ignition transient, (b) training never covered this state, or (c) QSS itself is numerically unsafe here regardless of “when” it is chosen. Distinguishing (a–c) is the main open question.

---

## 5. Hypotheses (ordered)

1. **QSS integrator (or QSS + `Tfreeze`) produces non-physical Y/T after autoignition** on this mechanism/IC; CVODE would have stayed in bounds (supported by cvodeOnly success).
2. **Missing species clipping / mass-fraction renormalization / enthalpy consistency** after QSS updates allows Y < 0, ΣY ≠ 1, or extreme radicals → JANAF `cp` explosion → T clip at 3500 K.
3. **RL policy is out-of-distribution or poorly calibrated for flame cells**, selecting QSS precisely where stiffness / heat release requires CVODE; adaptive mode therefore cannot recover once QSS has poisoned the state (`τ_dec` hold delays any switch).
4. **Secondary:** once thermo is NaN/Inf, `FOAM_SIGFPE` turns soft numerical failure into hard abort (qssOnly in `PBiCGStab`, rlAdaptive in `omega`). Disabling SIGFPE would hide, not fix, the physics/numerics issue.
5. **Less likely as root cause:** MPI decomposition, LibTorch load, or CVODE-only wiring — contradicted by successful cvodeOnly and clean policy load logs.

---

## 6. Questions for the expert

1. Is this QSS implementation known to be unsafe through ignition for n-dodecane / this skeletal mechanism at 10 atm with `Tfreeze true` and `itermax 2`?
2. Should there be hard guards before accepting a QSS update (ΣY, Yᵢ ≥ 0, ΔT limits, fallback to CVODE on failure)?
3. For RL: should hot / high-|ω| cells be **forced CVODE** regardless of policy, or should training include these 2D ignition states?
4. Is the T=3500 K clip coming from OpenFOAM thermo bounds, and should hitting it abort chemistry with a recoverable fallback instead of continuing?
5. Recommended minimal repro: single-cell / 0D restart from a dumped near-ignition state with QSS-only vs CVODE-only?

---

## 7. Artifacts to inspect

Base directory:

`OPENFOAM_PATH/validation/zeroD/e17_remote_runs/smoke_20260719_211924/`

| Artifact | Content |
|----------|---------|
| `cvodeOnly/log.*`, `fields_ascii/` | Successful reference |
| `qssOnly/log.qssOnly` | Ignition + cp runaway + PBiCGStab FPE |
| `rlAdaptive/log.rlAdaptive` | Same thermo path + CVODE `h→1e-78` + `omega` FPE |
| `rlAdaptive/rl_decisions.csv` | Per-cell flags / conf / T at each τ_dec |
| `rlAdaptive/rl_usage_summary.json` | Aggregate CVODE/QSS counts |
| `rlAdaptive/fields/*/solverFlag` | `uniform 0` → `uniform 1` |
| `*/chemistryProperties`, `*/controlDict` | Exact run settings |
| `ISSUES.md` | Shorter campaign notes |

---

## 8. Bottom line

**Same physical/numerical failure in qssOnly and rlAdaptive after ignition; cvodeOnly proves the case is solvable.** RL did select solvers (initially CVODE, then mesh-wide QSS), but at ignition it was effectively QSS-dominated and did not prevent the blow-up. Stabilizing **QSS post-ignition** and/or **forcing CVODE on flame / invalid states** is the highest-leverage next step; improving policy alone will not help if QSS updates can leave the CFD state irreparable within one `τ_dec` window.

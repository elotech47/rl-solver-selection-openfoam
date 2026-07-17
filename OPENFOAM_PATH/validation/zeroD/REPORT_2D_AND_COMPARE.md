# Report: 2D reactingFoam H6 fix + CVODE/QSS comparison

**Date:** 2026-07-17  
**Workspace:** `OPENFOAM_PATH/`

---

## What was broken (recap)

OpenFOAM’s `hePsiThermo::correct()` inverts temperature with `mixture.THE(h,p,T)` on a **JANAF-coefficient blend** (`multiComponentMixture::cellMixture`). For Luo n-dodecane runaway mixtures that blend’s `Cp` collapses / goes negative while the physical `Σ Yi·Cp_i` stays ~1400 J/(kg·K). That crashed 0D chemFoam mid-ignition (E8 H6). The same `thermo.correct()` sits at the end of reactingFoam’s `EEqn.H`, so **2D would hit the same failure** as soon as a cell entered thermal runaway.

---

## What we did to make 2D work

### 1. Local `reactingFoamDebug` (same fix class as chemFoam)

| Item | Path |
|------|------|
| Solver | `applications/solvers/reactingFoam/` → `platforms/.../bin/reactingFoamDebug` |
| Energy patch | `EEqn.H` calls `#include "massWeightedCorrect.H"` instead of bare `thermo.correct()` |
| Algorithm | Per cell: Newton on `Σ Yi·Hs_i(T) = he` (EEqn solution); set `he` briefly to blended `Hs(T)` so stock THE is a no-op; `thermo.correct()` refreshes `psi`/μ/α; restore `he` |

No Y/T clipping, no tolerance loosening, installed ESI tree untouched.

### 2. Bootstrapped `cases/opposedJet_2D`

- Mesh/BCs from ESI `counterFlowFlame2D`
- Luo foam `reactions`/`thermo`, `inertSpecie n2`
- Species fields `nc12h26`, `n2`, `o2` (fuel / air patches)
- T: fuel 300 K, air 1100 K, domain 800 K
- `application reactingFoamDebug`; libs load custom CVODE/QSS

### 3. Smoke verification

```text
reactingFoamDebug  endTime=2e-5
→ End (20 steps), min/max(T)=300,1100 every step, no Newton FATAL
```

Log: `cases/opposedJet_2D/log.reactingFoam`

This is a **startup/energy-path smoke**, not a full autoignition campaign. Full opposed-jet / coflow production runs still need mesh refinement, strain-rate setup, and longer `endTime`.

### 4. 0D acceptance (already done; required before 2D)

MidT with `chemFoamDebug` mass-weighted T: stock ode, cvode, qss all to equilibrium; OF-CVODE ign within **0.56%** of Python.

---

## CVODE vs QSS — OpenFOAM vs Python (MidT_MidP)

**IC:** 800 K, 10 atm, Z≈0.062, Luo n-dodecane, Δt=1e−6, t_end=3.5 ms  
**Python:** Cantera IdealGasConstPressureReactor (CVODE) + handoff `qss-integrator` (α-QSS)  
**OpenFOAM:** `chemFoamDebug` + custom `cvode` / `qss` chemistry solvers  

### Ignition delay (T ≥ 1200 K)

| Solver | τ_ign [ms] | T_end [K] | vs Python CVODE |
|--------|------------|-----------|-----------------|
| Python CVODE | **2.156** | 2601 | — |
| Python QSS | 2.310 | 2612 | +7.1% (late) |
| OpenFOAM CVODE | **2.144** | 2609 | **−0.56%** (PASS ≤1%) |
| OpenFOAM QSS | 1.949 | 2631 | −9.6% (early; expected class) |

QSS early bias in OF is the known behavior you already see in the Python baseline campaigns; **not** treated as a defect here.

### Graphic

![CVODE vs QSS — OF and Python](validation/zeroD/cvode_qss_compare/cvode_qss_of_vs_python.png)

Also: `cvode_qss_of_vs_python.pdf`, `trajectories.npz`, `summary.json`  
Regenerate: `conda activate rmg_env && python validation/zeroD/plot_cvode_qss_compare.py`  
(handoff must be `pip install -e handoff/`; script stubs `SundialsPy` on import because this OpenMPI build aborts on unused `SundialsPy` init — QSS only needs `qss-integrator`.)

---

## How to run

```bash
# 0D MidT (fixed chemFoam)
export FOAM_USER_APPBIN=.../platforms/linuxARM64GccDPInt32Opt/bin
chemFoamDebug   # cases/chemFoam_0D

# 2D opposed-jet smoke
cd cases/opposedJet_2D
blockMesh
reactingFoamDebug
```

---

## Still open for production 2D

- Longer opposed-jet / coflow autoignition with cvode vs qss vs RL maps  
- Same mass-weighted path is in the **solver**; any other reactingFoam-family app needs the same include (or a reactionThermo-level fix)  
- Coflow case still scaffold-only (`cases/coflow_2D`)

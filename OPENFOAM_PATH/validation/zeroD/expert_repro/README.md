# Expert repro: chemFoam MidT_MidP crash after ignition

**OpenFOAM:** ESI v2312 (`opencfd/openfoam-default:2312`)  
**Case:** single-cell `chemFoam`, Luo n-dodecane (106 species / 678 rxns)  
**IC:** MidT_MidP — T=800 K, p=10 atm, Z≈0.062 (mole: o2/n2/nc12h26)  
**Platform that produced these logs:** native `linux/arm64` on Apple Silicon (~14 s CVODE, ~3 s QSS to crash)

---

## Symptom

Both custom chemistry solvers (`cvode`, `qss`) integrate cleanly through ignition
(T≥1200 K), then **abort in the outer chemFoam loop** during the thermal runaway:

```
FOAM FATAL ERROR: Maximum number of iterations exceeded: 100
  when starting from T0:~1700–1830
  From Foam::species::thermo<...>::T(...)   # h → T Newton
```

Preceded by JANAF warnings with **nonsense T** (e.g. −1089 K, −2999 K). Those are
Newton iterates, not the physical gas temperature written to `chemFoam.out`
(which is still ~1700–1800 K one step earlier).

| Solver | Last good sample | Abort at | Ignition (T≥1200) |
|--------|------------------|----------|-------------------|
| CVODE  | t≈2.265 ms, T≈1831 K | `hEqn` / `thermo.correct()` | 2.141 ms |
| QSS    | t≈1.986 ms, T≈1721 K | same | 1.892 ms |

Full logs: `logs/cvode_arm64.log`, `logs/qss_arm64.log`  
Short crash tails: `logs/*_excerpt.txt`  
T(t) histories: `logs/*.out`

---

## Why we think it is a chemFoam coupling issue (not the ODE alone)

chemFoam (ESI) does **not** take T from the chemistry ODE. Per timestep it:

1. `dtChem = chemistry.solve(deltaT)` — our solver updates cell concentrations + T internally  
2. `YEqn.H` — applies `chemistry.RR` to species mass fractions  
3. Accumulates `integratedHeat += Qdot * deltaT` with `Qdot = chemistry.Qdot()[0]/rho`  
4. `hEqn.H` — sets `h = h0 + integratedHeat` (constant-pressure), then `thermo.correct()`  
5. `thermo.correct()` Newton-solves T from enthalpy + current Y

So the abort is in step 4–5. The ODE may return a sensible T, but chemFoam
**recomputes T from h** built from `Qdot`/`RR`. If those are inconsistent with
the Y change (or one window dumps too much heat), Newton fails.

Stock ESI energy ODE (for comparison) is:

```cpp
// StandardChemistryModel::derivatives — constant pressure
dT/dt = - Σ_i ha_i(p,T) * ω̇_i   / (ρ * cp)
```

Our current solvers mirror that (`ha`, mole-basis `cp`). Earlier we used
`Hc`-only heat release; that was wrong and was fixed. **Crash still happens.**

Raising JANAF `Thigh` to 5000 for all species (case `constant/thermo`) changed
the warning from `300→3000` to `300→5000` but did **not** stop the abort.

---

## Questions for the expert

1. For a custom `chemistrySolver` used with chemFoam, must `RR` / `Qdot` satisfy
   a consistency relation that stock `ode`/`seulex` automatically provides?
2. Is chemFoam’s `integratedHeat` + `h = h0 + integratedHeat` path known to be
   fragile for stiff 100+ species ignition at Δt ~ 1e−6 s?
3. Preferred fix for 0D validation:
   - (A) trust ODE T and bypass / replace chemFoam `hEqn`, or  
   - (B) keep chemFoam and force much smaller Δt through runaway, or  
   - (C) something else (e.g. reconstruct h from ODE state instead of Qdot)?

Secondary (parity, not crash): OF QSS ignition is ~18% early vs our Cantera/QSS
handoff reference; OF CVODE is within ~1%. See `refs/`.

---

## Package layout

```
expert_repro/
  README.md                 # this file
  case/                     # MidT chemFoam case (no time dirs; chemFoam builds 1-cell mesh)
    constant/{chemistryProperties,initialConditions,reactions,thermo,thermophysicalProperties}
    system/{controlDict,fvSchemes,fvSolution}
    Allclean
  logs/
    cvode_arm64.{log,out,excerpt.txt}
    qss_arm64.{log,out,excerpt.txt}
  src/                      # custom solvers at crash-time revision
    cvodeSolver.{H,C}
    qss.{H,C}  qss_int.{H,C}  qssChemistrySolvers.C
  refs/
    handoff_MidT.json       # Python/Cantera reference ignitions
    compare_report.json     # OF vs handoff (pre-crash ignition times)
```

Full project (build scripts, SUNDIALS, Docker notes) lives one level up at
`OPENFOAM_PATH/`. Native arm64 libs: `platforms/linuxARM64GccDPInt32Opt/lib/`.
SUNDIALS: `opt/sundials-arm64/`.

---

## How to reproduce (native arm64 recommended)

```bash
# From OPENFOAM_PATH on Apple Silicon / linux arm64:
docker run --rm --platform=linux/arm64 --entrypoint /bin/bash \
  -v "$PWD:/work" -w /work/cases/chemFoam_0D \
  opencfd/openfoam-default:2312 \
  -lc 'source /usr/lib/openfoam/openfoam2312/etc/bashrc
       export FOAM_USER_LIBBIN=/work/platforms/$WM_OPTIONS/lib
       export SUNDIALS_DIR=/work/opt/sundials-arm64
       export LD_LIBRARY_PATH=$SUNDIALS_DIR/lib:$FOAM_USER_LIBBIN:$LD_LIBRARY_PATH
       bash Allclean
       foamDictionary constant/chemistryProperties -entry chemistryType/solver -set cvode
       # endTime 0.0035, deltaT/maxDeltaT 1e-6 already set
       chemFoam 2>&1 | tee log.chemFoam.cvode'
```

Same with `solver qss`. Expect abort near the times in the table above.

To rebuild libs: `tools/build_libs.sh` inside the same container after
`source .../bashrc`.

---

## Key source pointers (ESI v2312)

| Piece | Path in image |
|-------|----------------|
| chemFoam loop | `applications/solvers/combustion/chemFoam/chemFoam.C` |
| heat update | `.../chemFoam/hEqn.H`, `solveChemistry.H` |
| stock energy ODE | `src/.../StandardChemistryModel.C` → `derivatives()` |
| h→T Newton | `src/.../thermoI.H` (~line 76) |

Our energy RHS (CVODE): `src/cvodeSolver.C` → `cvodeRhs`  
Our energy RHS (QSS): `src/qss.C` → `QssCellOde::odefun`  
chemFoam Qdot path still uses `BasicChemistryModel::Qdot()` from `RR` / Hc.

---

## Timing note (for context)

Under QEMU `linux/amd64` the same MidT run was ~6 min (CVODE). Native arm64 is
~14 s. Most of the “0D is impossibly slow” report was emulation, not physics.

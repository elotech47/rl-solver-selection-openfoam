# How this project solves chemically reacting flow

A guided tour for new contributors — including people new to combustion.

**What we build:** OpenFOAM (ESI **v2312**) extensions that integrate stiff chemical kinetics with two solvers (**CVODE** and **α-QSS / CHEMEQ2**) and optionally choose between them **per cell** with a trained RL policy — without retraining the policy for CFD.

**Canonical tree:** everything Foam-related lives under [`OPENFOAM_PATH/`](../../OPENFOAM_PATH/) (Docker mount ≡ `/work`).

---

## 0. Intuition (no combustion background required)

### 0.1 What “reacting flow” means here

We simulate a gas mixture that:

1. **Flows** (velocity, pressure, density — fluid mechanics).  
2. **Diffuses / conducts heat** (transport).  
3. **Chemically reacts** — hundreds of elementary reactions among ~100 species (kinetics).

Chemistry is often the expensive part: some species change on nanosecond scales while the flow evolves on microseconds–milliseconds. That **stiffness** is why we need special ODE integrators (CVODE, QSS), not a naïve forward Euler step on every species.

### 0.2 Mass fractions and temperature

- **Species mass fraction** \(Y_i\): mass of species \(i\) divided by mixture mass. \(\sum_i Y_i = 1\).  
- **Temperature** \(T\): set by energy conservation and the heat released/absorbed by reactions.  
- **Pressure** \(p\) and **density** \(\rho\): linked by an equation of state (ideal gas in our cases).

Chemistry does not invent mass: it **rearranges** atoms among molecules. Heat release appears because product molecules sit at different enthalpies than reactants.

### 0.3 0D vs “1D” vs our 2D cases

| Setup | What varies in space? | Role in this project |
|-------|------------------------|----------------------|
| **0D reactor** (`chemFoam`) | Nothing — one well-stirred cell | Ignition delay, integrator & policy validation |
| **1D opposed jet** (Ember reference) | Only along the gap between two nozzles | Paper / cross-check target along the centerline |
| **2D opposed jet** (`opposedJet_*`) | Planar mesh; flame looks 1D on the midplane | Production CFD demos (E17 / E18) |

So when docs say “vs Ember 1D,” they mean **centerline profiles**, not that OpenFOAM only has a 1D mesh.

```text
  Fuel jet ──►  |  stagnation / flame sheet  |  ◄── Air jet
               ←—————— gap L ——————→
```

---

## 1. Equations (what we are discretizing)

### 1.1 Chemical kinetics (every cell)

For species concentrations \(c_i\) (kmol/m³) at fixed pressure (our chemistry integrators match the **constant-pressure** training setup):

\[
\frac{\mathrm{d}c_i}{\mathrm{d}t} = \dot{\omega}_i(T,p,\mathbf{c}),
\qquad
\frac{\mathrm{d}T}{\mathrm{d}t} = f_{\text{energy}}(\dot{\omega}, h_i, c_p,\ldots)
\]

\(\dot{\omega}_i\) comes from the **mechanism** (Arrhenius rates, third-body, fall-off, etc.).  
α-QSS needs **creation/destruction** rates \(q_i,d_i\) from forward/reverse progress rates — **not** a sign-split of the net rate (see `instruction.md` ground rules).

### 1.2 Coupling chemistry → CFD (OpenFOAM pattern)

OpenFOAM’s chemistry model integrates each cell over a window \(\Delta t_{\mathrm{chem}}\) and returns **effective reaction rates** that the transport equations consume (ESI `StandardChemistryModel` pattern):

\[
\mathrm{RR}_i \approx \rho\,\frac{Y_i^{n+1}-Y_i^{n}}{\Delta t_{\mathrm{chem}}}
\]

Heat release for the energy equation is built from \(\mathrm{RR}_i\) and enthalpies of formation:

\[
\dot{Q} = -\sum_i \mathrm{RR}_i\, h_{f,i}
\quad\text{(sign convention as in Foam; magnitude = chemical heat)}.
\]

Standing diagnostic in this repo: compare integrator \(T\) to CFD \(T\) after transport applies \(\mathrm{RR}\) (`Tconsistency`).

### 1.3 Multi-dimensional conservation (opposed jet / `reactingFoam`)

High level (compressible reacting Navier–Stokes; details in Foam’s `UEqn` / `YEqn` / `EEqn`):

| Equation | Idea |
|----------|------|
| Continuity | Mass conservation for \(\rho\) |
| Momentum | \(\partial_t(\rho\mathbf{U}) + \nabla\cdot(\rho\mathbf{U}\mathbf{U}) = -\nabla p + \ldots\) |
| Species | \(\partial_t(\rho Y_i) + \nabla\cdot(\rho\mathbf{U} Y_i) = \nabla\cdot(\mu_{\mathrm{eff}}\nabla Y_i) + \mathrm{R}(Y_i)\) |
| Energy | Enthalpy (or internal energy) with conduction/diffusion and \(\dot{Q}\) |

**Operator splitting:** each CFD step, chemistry advances composition over \(\Delta t\) (possibly subcycled), then flow/transport uses the resulting \(\mathrm{RR}\) and \(\dot{Q}\).

---

## 2. 0D: how `chemFoam` solves it

### 2.1 What the app does

Application binary: **`chemFoamDebug`**  
Case: [`OPENFOAM_PATH/cases/chemFoam_0D/`](../../OPENFOAM_PATH/cases/chemFoam_0D/)

There is **no mesh flow** — one cell. The loop is essentially:

1. **`solveChemistry`** — integrate the stiff ODE for \(\Delta t\)  
2. **`YEqn`** — update mass fractions from chemistry \(\mathrm{RR}\)  
3. **`hEqn` / energy** — update enthalpy from chemical heat  
4. **`pEqn`** — close thermodynamics (`constantProperty pressure` or `volume`)

Sources: `applications/solvers/chemFoam/{chemFoam.C,YEqn.H,hEqn.H,pEqn.H,solveChemistry.H}`.

### 2.2 Initial conditions (easy to get wrong)

File: `cases/chemFoam_0D/constant/initialConditions`

Must look like:

```c++
constantProperty pressure;   // or volume
fractionBasis   mole;        // or mass
fractions
{
    n2      ...;
    o2      ...;
    nc12h26 ...;
}
p   1013250;   // Pa (example: 10 atm)
T   800;       // K
```

Do **not** put bare `Yi` keys at the top level of this dictionary (Foam will mis-parse and \(\sum Y\) will look insane). See `AGENTS.md`.

### 2.3 Why 0D matters for this project

Parity ladder (`instruction.md`):

1. Rate parity (OF vs Cantera)  
2. Single ~1 µs step parity (QSS & CVODE)  
3. **0D trajectory** ignition curves  
4. Then 1D/2D flame profiles  

If 0D is wrong, CFD will be wrong for the same reason — fix 0D first.

---

## 3. Multi-D / opposed jet: how `reactingFoam` solves it

### 3.1 Solver and loop

Binary: **`reactingFoamDebug`**  
Cases:

- [`cases/opposedJet_2D/`](../../OPENFOAM_PATH/cases/opposedJet_2D/) — E17 smoke (gap \(L=0.02\,\mathrm{m}\))  
- [`cases/opposedJet_E18/`](../../OPENFOAM_PATH/cases/opposedJet_E18/) — E18 Ember-matched gap \(L=0.008\,\mathrm{m}\)

PIMPLE outer loop (schematic): `rhoEqn` → `UEqn` → chemistry/`YEqn` → `EEqn` → `pEqn`.

`reaction->correct()` runs the chemistry model; species equations then use `reaction->R(Yi)`; energy uses `reaction->Qdot()`.

### 3.2 “1D flame” reading of a 2D run

On the midplane (or centerline strip), plot \(T(x)\), \(Y_{\mathrm{OH}}(x)\), mixture fraction, etc. Those curves are what we compare to **Ember 1D** opposed-jet solutions (`validation/oned_crossref/`).

### 3.3 Typical E18 Stage split (why chemistry is often off at first)

Documented in `validation/zeroD/e18_prep/`:

1. **Stage 1 — cold mix:** chemistry **off**, establish a frozen mixing field.  
2. **Stage 2 — chemistry restart:** turn chemistry **on**, restart from freeze time with `cvodeOnly` / `qssOnly` / `rlAdaptive`.

Checked-in `opposedJet_E18` may ship with `chemistry off` for Stage 1; Stage 2 scripts rewrite `chemistryProperties`.

---

## 4. The chemical mechanism

### 4.1 What a “mechanism” is

A mechanism is a list of:

- **Species** (thermodynamics: NASA polynomials → \(c_p\), \(h\), \(s\))  
- **Reactions** (kinetics: Arrhenius parameters, third bodies, pressure dependence)  
- **Transport** (viscosities, diffusivities — Sutherland / polynomial fits)

This project uses **Luo n-dodecane**: **106 species, 678 reactions** (same YAML as the CnF / handoff paper). Do **not** swap in a different dodecane mechanism (e.g. Pele Lu-53).

### 4.2 How files get into OpenFOAM

Pipeline (see [`mechanisms/CONVERSION.md`](../../OPENFOAM_PATH/mechanisms/CONVERSION.md)):

```text
n-dodecane.yaml  →  Chemkin (chem.inp, therm.dat, …)  →  chemkinToFoam
                 →  mechanisms/foam/{reactions,thermo}
                 →  copied into case constant/
```

Cases point at Foam files via `thermophysicalProperties`:

```c++
foamChemistryFile       "<constant>/reactions";
foamChemistryThermoFile "<constant>/thermo";
```

**Production thermo:** Option R JANAF refit (`Thigh = 3500` K, etc.) under `mechanisms/refit/` — important for high-\(T\) stability after ignition.

---

## 5. Chemistry solvers and RL selection

### 5.1 Two integrators (the “arms”)

| Solver | Library | Character |
|--------|---------|-----------|
| **CVODE** (SUNDIALS BDF) | `libcvodeChemistrySolver.so` | Robust, expensive on stiff cells |
| **α-QSS / CHEMEQ2** | `libqssChemistrySolver.so` | Fast when quasi-steady radicals apply; can fail / need rescue |

Stock Foam `ode` + `seulex` exists for smoke tests; **production CFD** uses the custom chemistry **method** below.

### 5.2 The `rl` chemistry model

Configured as:

```c++
chemistryType
{
    solver  ode;
    method  rl;     // loads librlChemistryModel.so
}
```

Implementation: [`src/rlChemistryModel/`](../../OPENFOAM_PATH/src/rlChemistryModel/).

| Mode | Behavior |
|------|----------|
| `cvodeOnly` | Always CVODE (Layer-1 sanitize still on) |
| `qssOnly` | Always attempt QSS + **guards**; reject → CVODE redo |
| `rlAdaptive` | **Policy** chooses CVODE vs QSS every \(\tau_{\mathrm{dec}}\) + **same guards** |

Unguarded stock `solver qss` is **retired for CFD** after E17.2 (still OK for some 0D algorithm studies).

### 5.3 E17.2 guards (why QSS does not silently poison the field)

When QSS runs under `method rl`:

1. **Layer 1 — sanitize inputs:** floor \(Y_i \ge 0\), renormalize \(\sum Y = 1\) (diagnostic `yClipMass`).  
2. **Integrate QSS** over the micro-window.  
3. **Layer 2 — accept/reject** raw output. Reject if any of:
   - \(Y_i < -\varepsilon_Y\)  
   - \(\lvert\sum Y - 1\rvert > \varepsilon_{\Sigma Y}\)  
   - \(\lvert\Delta T\rvert > dT_{\max}\) over the window  
   - \(T \notin [T_{\min}, T_{\max}]\)  
4. On reject: **restore** pre-QSS state, **redo with CVODE**, increment `qssFallbackCount`. That window **counts as CVODE** in usage.

Progress logs may print `rlFallbackReasons` with percentages per check.

Defaults and E18 notes: `AGENTS.md`, `validation/zeroD/e17_2/E17_2_GATES.md`. Cold fuel at 300 K needs \(T_{\min}\) **≤ 300** (E18 uses 250), or nearly every cold cell “falls back” as `T_bounds`.

### 5.4 The RL policy (solver selection)

**Actions**

- `0` → CVODE  
- `1` → QSS  
- Softmax confidence \(< 0.6\) → force CVODE  

**Observation (19-D)** — order fixed in `policy_manifest` / `policyFeatures.H`:

1. \(T\) normalized  
2. \(\log_{10} Y\) for 8 key species: OH, H₂O, O₂, H₂, H₂O₂, O, H, N₂  
3. \(p\) normalized  
4. Nine **Δlog₁₀** features (T + keys) — **differences**, not divided by \(\Delta t\)

**Decision interval (physical chemistry time):**

\[
\tau_{\mathrm{dec}} = N_{\mathrm{steps}} \times \Delta t_{\mathrm{ref}}
\quad\text{(default } 20 \times 10^{-6}\,\mathrm{s} = 20\,\mu\mathrm{s}\text{)}
\]

Decisions land on this chemistry clock (E16.5), not “every CFD step” unless you set \(\tau_{\mathrm{dec}}\) accordingly. CFD \(\Delta t \approx 10^{-5}\) with \(\tau_{\mathrm{dec}}=2\times10^{-5}\) ⇒ decide roughly every **two** steps.

**Artifacts**

- TorchScript: `OPENFOAM_PATH/policy/policy.ts`  
- Foam dict: `OPENFOAM_PATH/policy/policy_manifest` (**snake_case** keys: `obs_dim`, `obs_rms_mean`, …)  
- Export: `tools/export_policy.py` + `tools/export_policy_manifest_foam.py` (`workon rlEnv`)

In Docker, `chemistryProperties` must quote container paths:

```c++
manifest     "/work/policy/policy_manifest";
torchScript  "/work/policy/policy.ts";
```

### 5.5 Where to flip modes

- Manual: case `constant/chemistryProperties` (`rl { mode ... }`, `guardCoeffs`, `qssCoeffs`, `cvodeCoeffs`)  
- Helper: `validation/zeroD/e17_configure_mode.sh`  
- E18 Stage 2: `validation/zeroD/e18_prep/stage2_configure_mode.sh`

`controlDict` must load:

```c++
libs ( "libqssChemistrySolver.so" "libcvodeChemistrySolver.so"
       "libpolicyRuntime.so" "librlChemistryModel.so" );
```

---

## 6. Mental model of one CFD chemistry call

```text
for each reacting cell:
  if mode == rlAdaptive and chemistry_time due for decision:
      build 19-D obs → TorchScript → action (or force CVODE if low conf)
  for chemistry micro-windows up to Δt:
      Layer-1 sanitize
      if action == QSS:
          integrate QSS
          if Layer-2 reject: restore; integrate CVODE; count fallback
          else: accept (floor Y for CFD)
      else:
          integrate CVODE
  pack RR_i and Qdot for transport
```

Usage line (MPI-reduced): `rlUsage` with `CVODE` / `QSS` / `fallbackCVODE` and `wall_chem` (see `AGENTS.md` for CPU-sum vs wall).

---

## 7. How to contribute safely

1. **Read** `instruction.md` ground rules (parity ladder, no rate rescaling, true \(q/d\) for QSS).  
2. **Change C++** under `src/`, then `wmake` inside Docker (`AGENTS.md` §2).  
3. **Validate 0D** before claiming CFD wins.  
4. **Never commit** Stage 2 dumps: `e18_prep/stage2_chem_*/`, `processor*`, huge logs (`.gitignore`). Commit scripts + small reports only.  
5. **Update** `DECISIONS.md` / `AGENTS.md` when you discover a new footgun.

### Quick pointers

| Topic | Path |
|-------|------|
| Spec | `OPENFOAM_PATH/instruction.md` |
| Agent footguns | `AGENTS.md` |
| Decisions log | `OPENFOAM_PATH/DECISIONS.md` |
| 0D case | `OPENFOAM_PATH/cases/chemFoam_0D/` |
| 2D cases | `OPENFOAM_PATH/cases/opposedJet_2D/`, `opposedJet_E18/` |
| RL model | `OPENFOAM_PATH/src/rlChemistryModel/` |
| QSS / CVODE | `src/qssChemistrySolver/`, `src/cvodeChemistrySolver/` |
| Policy runtime | `src/policyRuntime/` |
| Mechanism conversion | `mechanisms/CONVERSION.md` |
| E17.2 gates | `validation/zeroD/e17_2/E17_2_GATES.md` |
| E18 prep | `validation/zeroD/e18_prep/README.md` |

---

## 8. Glossary

| Term | Meaning |
|------|---------|
| Stiffness | Timescales in the ODE span many orders of magnitude |
| CVODE | Implicit BDF ODE solver (SUNDIALS) — accurate/robust |
| α-QSS | Quasi-steady-state integrator (CHEMEQ2) — cheap when valid |
| \(\mathrm{RR}\) | Effective species source for CFD after a chemistry window |
| \(\tau_{\mathrm{dec}}\) | Policy decision period in chemistry time |
| Guard / fallback | Reject bad QSS state and redo with CVODE |
| Mixture fraction \(Z\) | Conserved scalar measuring fuel–air mixing |
| JANAF / NASA7 | Thermodynamic polynomial fits for \(c_p,h,s\) |

---

*This wiki complements, and does not replace, `instruction.md`. When they disagree on an implementation detail, prefer the code + `DECISIONS.md`, then update this page.*

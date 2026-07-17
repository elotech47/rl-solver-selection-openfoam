# QSS Integrator Failure — Static Diagnosis Report

**Scope:** Static code inspection of `ReactorQSS` in `PelePhysics` (fork `elotech47/PelePhysics`, branch `development`), compared against `ReactorRK64`, `ReactorCvode`, and CEPTR mechanism output for `dodecane_lu_qss`.

**Brief:** See [`diagnosis.md`](diagnosis.md) for the original inspection tasks and ground rules.

---

## 1. Root-cause verdict

**Most likely cause (single): sign-split of net chemistry rates instead of true separated production/destruction rates.**

`ReactorQSS::CellOde::odefun` calls `eos.RTY2WDOT` (net ω̇ in g/cm³/s), adds external forcing, then does `q = max(0, rhs)`, `d = max(0, -rhs)`. That destroys the stiffness information α-QSS needs whenever q and d nearly cancel — exactly the stiff-radical regime in a counterflow flame. This alone explains why Cantera (true `creation_rates`/`destruction_rates`) and Ember (pure kinetics, no advection forcing) work, while Pele fails.

```cpp
// ReactorQSS.cpp:165-171
for (int n = 0; n < NUM_SPECIES; n++) {
  const amrex::Real rhs_n = wdot[n] + m_rYsrc[n];
  q[n] = (rhs_n > 0.0) ? rhs_n : 0.0;
  d[n] = (rhs_n < 0.0) ? -rhs_n : 0.0;
  rhoesrc -= rhs_n * ei[n];
}
```

The header documents this explicitly:

```cpp
// ReactorQSS.H:14-16
// where q >= 0 (production) and d >= 0 (destruction). The production/destruction
// split uses a sign-split of the net chemistry RHS: q = max(0, wdot + src),
// d = max(0, -(wdot + src)).
```

### Ranked runner-ups

| Rank | Issue | Why it matters in Pele 2D |
|------|-------|---------------------------|
| 1 | **Net-rate sign-split for chemistry** (above) | Wrong τᵢ everywhere in flame zone; dominant root cause |
| 2 | **External forcing folded into sign-split q/d** | `rYsrc` can be negative and dominate in near-inert cells; corrupts τᵢ and breaks non-negativity semantics (`ReactorQSS.cpp:166–168`) |
| 3 | **Temperature evolved via sign-split Padé** | RK64/Cvode use net `Tdot`; QSS sign-splits `Tdot` (`ReactorQSS.cpp:179–181` vs `ReactorUtils.H:413–414`) |
| 4 | **Failed cells frozen at initial state** | `integrate_cells` returns without writing on failure (`ReactorQSS.cpp:255–266`); SDC can diverge silently |
| 5 | **CPU-only reactor** | GPU builds abort immediately (`ReactorQSS.cpp:310–315`) |

Mechanism code already exposes per-reaction forward/reverse progress rates (`comp_qfqr`, `CKKFKR`) but QSS never calls them — it only uses net `productionRate` via `RTY2WDOT`.

---

## 2. Findings table

| Task | Verdict | Severity | Evidence |
|------|---------|----------|----------|
| **1 — External forcing** | **BUG** | **HIGH** | Forcing is read (`flatten` → `m_rYsrc`, `m_rhoesrc_ext`, `ReactorQSS.cpp:244–247`) but folded into sign-split q/d (`166–168`), not applied as a separate explicit increment like RK64's additive `ydot` (`ReactorUtils.H:407–410`). Energy budget uses combined `rhs_n` (`170`), matching RK64's net formulation — energy coupling is structurally OK; the sign-split on species is the defect. |
| **2 — qᵢ/dᵢ construction** | **BUG** | **CRITICAL** | Calls `eos.RTY2WDOT` → `CKWC` → `productionRate` (net ω̇, `Fuego.H:240–252`, `mechanism.H:11811+`). Sign-split at `ReactorQSS.cpp:166–168`. Per-reaction `qf`/`qr` available via `comp_qfqr` (`mechanism.H:9290`) and `CKKFKR` (`mechanism.cpp:207–231`) but unused. |
| **3 — Units audit** | **OK** | Low | State is `ρYᵢ` [g/cm³] + `T` [K] (`ReactorQSS.cpp:93–94, 121–126`). `RTY2WDOT` returns g/cm³/s (`Fuego.H:250–252`). `τᵢ = dt·dᵢ/yᵢ` uses `ρYᵢ` as `yᵢ` (`qss_int.cpp:134`) — dimensionally consistent. No stray 1e3/1e6 factors in QSS path. `CKWC` SI bridge (1e6) is internal to mechanism, same as all reactors. |
| **4 — Energy formulation** | **SUSPICIOUS** | **MEDIUM** | Branches on `reactor_type` for `Ei`/`Hi` and `Cv`/`Cp` (`ReactorQSS.cpp:152–158`) — correct. But `Tdot` is sign-split into `q_T`/`d_T` (`179–181`) whereas RK64 uses net `ydot[T] = rhoesrc·ρ⁻¹/Cv` (`ReactorUtils.H:413–414`). Final `T` overwritten by `REY2T`/`RHY2T` in `unflatten` (`ReactorUtils.H:280–288`) — same pattern as RK64. In-step T evolution is the concern. |
| **5 — Robustness / substepping** | **SUSPICIOUS** | **MEDIUM** | Species floor `ymin=1e-20` (`qss_int.cpp:56`); T bounded [250, Tmax] K (`ReactorQSS.cpp:223–225`). `clean_init_massfrac` optional via `ode.clean_init_massfrac`. NaN: `AMREX_ASSERT(notnan(...))` only (`qss_int.cpp:24–29, 122–125`); no cell-level catch. Adaptive internal substeps via CHEMEQ2 loop (`qss_int.cpp:110–262`, default `dtmax=1e-6`). Failure → freeze cell (`ReactorQSS.cpp:255–266`). `itermax=2` matches CHEMEQ2 default. |
| **6 — Interface vs RK64** | **SUSPICIOUS** | **MEDIUM–HIGH** | See structural diff below. Key gaps: CPU-only, no GPU `ParallelFor`, returns `0` not avg substeps, freezes failed cells, sign-split RHS vs `fKernelSpec` net RHS. |
| **7 — Standalone repro** | **OK (sketch)** | Bonus sketch in [§7](#7-bonus--standalone-repro-sketch-task-7); not compiled (AMReX/mechanism coupling). |

---

## 3. Structural diff vs `ReactorRK64`

| Aspect | `ReactorRK64` | `ReactorQSS` |
|--------|---------------|--------------|
| RHS | `fKernelSpec`: net `ydot = ω̇ + rYsrc` (`ReactorUtils.H:407–414`) | Sign-split `q,d` from `ω̇ + rYsrc` (`ReactorQSS.cpp:166–181`) |
| State | `[ρY₀…ρYₙ₋₁, T]` per cell | Same (`ReactorQSS.H:18`) |
| Forcing arrays | `rYsrc_in`, `rEner_src_in` | Same via `flatten` (`ReactorQSS.cpp:344–347`) |
| Energy end-update | `ρE += dt·ρė_ext` (`ReactorRK64.cpp:298`) | Same via `box_unflatten` (`ReactorUtils.H:278`) |
| T recovery | `REY2T`/`RHY2T` after integrate (`ReactorRK64.cpp:301–307`) | Same (`ReactorUtils.H:280–288`) |
| Substepping | RK64 error-controlled loop (`ReactorRK64.cpp:100–137`) | CHEMEQ2 adaptive loop (`qss_int.cpp:110–262`) |
| GPU | `ParallelFor` on device | **Aborts on GPU** (`ReactorQSS.cpp:310–315`) |
| Return value | Avg RK substeps (`ReactorRK64.cpp:319`) | Always `0` (`ReactorQSS.cpp:373`) |
| Failure handling | RK continues (no freeze) | **Freezes cell** (`ReactorQSS.cpp:255–266`) |

### RK64 reference for forcing (additive, not sign-split)

```cpp
// ReactorUtils.H:407-414
for (int n = 0; n < NUM_SPECIES; n++) {
  const amrex::Real cdot_rYs =
    cdots_pt[n] + rYs[spec_index<OrderType>(n, icell, ncells)];
  ydot_d[vec_index<OrderType>(n, icell, ncells)] = cdot_rYs;
  rhoesrc -= cdot_rYs * ei_pt[n];
}
ydot_d[vec_index<OrderType>(NUM_SPECIES, icell, ncells)] =
  rhoesrc * (rho_pt_inv / Cv_pt);
```

---

## 4. Minimal fix plan (smallest diff first)

### Fix 1 — True chemistry q/d from per-reaction rates (CRITICAL)

- **Where:** `ReactorQSS::CellOde::odefun` (`PelePhysics/Source/Reactions/ReactorQSS.cpp:139–171`)
- **What:** Replace `RTY2WDOT` + sign-split with stoichiometric assembly from `comp_qfqr` (or `CKKFKR` on CPU). For each reaction `j` with forward progress `qf[j]` and reverse `qr[j]`:
  - Reactants: `d[i] += νᵢⱼ·qf`, `q[i] += νᵢⱼ·qr`
  - Products: `q[i] += νᵢⱼ·qf`, `d[i] += νᵢⱼ·qr`
  - Use `CKINU` for stoichiometry (`mechanism.cpp:34`)
- **Units:** `comp_qfqr` works in mol/cm³/s; multiply by `mw(i)` for g/cm³/s to match `ρY` state.
- **Risk:** Low logic risk, moderate implementation effort; must handle QSS-species path (`sc_qss`) already inside `comp_qfqr`.

### Fix 2 — Decouple external forcing from sign-split (HIGH)

- **Where:** `odefun` + `QssIntegrator` step callback, or post-substep in `integrate_cells`
- **What:** Compute q/d from **chemistry only** (Fix 1). Apply forcing explicitly per internal substep:

  ```cpp
  y[i] += dt_sub * m_rYsrc[i];           // species
  // T: use net Tdot from energy residual with chemistry+forcing, NOT sign-split
  ```

  Or RK64-style: keep net `rhs_n` for energy/T, but never sign-split it for QSS species update.

- **Risk:** Low if Fix 1 is done first; this is the Pele-specific fix 0D/Ember didn't need.

### Fix 3 — Temperature: net derivative, not sign-split (MEDIUM)

- **Where:** `ReactorQSS.cpp:173–181`, `qss_int.cpp:134` (T index)
- **What:** Set `enforce_ymin[NUM_SPECIES]=0` for T. Provide QSS with net `Tdot` as a single positive/negative ODE, or integrate T outside QSS Padé (explicit Euler on net `Tdot` matching `fKernelSpec`).
- **Risk:** Medium — needs validation against 0D reference.

### Fix 4 — Failure policy (LOW)

- **Where:** `ReactorQSS.cpp:255–266`
- **What:** On `integrateToTime` failure, fall back to RK64 subcycling for that cell, or at minimum log + abort rather than silent freeze.
- **Risk:** Low.

### Fix 5 — CEPTR helper (optional, cleaner long-term)

- **Where:** `PelePhysics/Support/ceptr/ceptr/production.py`
- **What:** Generate `productionRateQD(amrex::Real* q, amrex::Real* d, ...)` alongside `productionRate`, using existing `comp_qfqr` + stoichiometry loop.
- **Risk:** Low runtime risk; requires mechanism regeneration.

---

## 5. Instrumentation patch

Drop into `ReactorQSS::CellOde::odefun` after q/d are computed (or after Fix 1, dump both true and sign-split for comparison):

```cpp
// --- QSS debug dump (add to CellOde as member: static int s_dump_count) ---
{
  static int s_dump_count = 0;
  const int k_dbg_species[] = {H_ID, O_ID, OH_ID, HO2_ID, H2O_ID, H2_ID, O2_ID, N2_ID};
  constexpr int n_dbg = 8;

  bool bad = !std::isfinite(T);
  amrex::Real rho_chk = 0.0;
  for (int n = 0; n < NUM_SPECIES; ++n) {
    rho_chk += massdens[n];
    const amrex::Real Yn = massdens[n] / rho_chk; // approximate
    if (!std::isfinite(Yn) || Yn < -1.e-8 || Yn > 1.0 + 1.e-8) bad = true;
  }
  if (bad && s_dump_count < 100) {
    std::ofstream dbg("qss_fail_dump.txt", std::ios::app);
    dbg << std::scientific << std::setprecision(16);
    dbg << "--- dump " << s_dump_count++ << " ---\n";
    dbg << "T=" << T << " rho=" << rho << " reactor_type=" << m_reactor_type << "\n";
    dbg << "rhoesrc_ext=" << m_rhoesrc_ext << "\n";
    for (int n = 0; n < NUM_SPECIES; ++n) {
      dbg << "  rhoY[" << n << "]=" << massdens[n]
          << "  rYsrc=" << m_rYsrc[n]
          << "  wdot=" << wdot[n]
          << "  q=" << q[n] << "  d=" << d[n];
      if (massdens[n] > 0.0)
        dbg << "  tau~=" << d[n] * 1.e-6 / massdens[n]; // rough; pass actual dt from integrate_cells
      dbg << "\n";
    }
    dbg << "key species (H,O,OH,HO2,H2O,H2,O2,N2):\n";
    for (int ki = 0; ki < n_dbg; ++ki) {
      int n = k_dbg_species[ki];
      dbg << "  sp" << n << ": Y=" << massfrac[n]
          << " wdot=" << wdot[n] << " q=" << q[n] << " d=" << d[n] << "\n";
    }
    dbg << "Tdot_q=" << q[NUM_SPECIES] << " Tdot_d=" << d[NUM_SPECIES] << "\n";
    dbg.close();
  }
}
```

For full replay, also log `dt_react` and cell index from `integrate_cells` (pass `icell` into `CellOde` via `setup`).

---

## 6. Open questions + workstation experiments

| Question | Experiment |
|----------|------------|
| No in-repo Python/Ember α-QSS reference found — does Pele `qss_int.cpp` match your Cantera implementation formula-for-formula? | Diff your Cantera/Ember `α(τ)`, predictor, corrector against `qss_int.cpp:140–190`; run matched 0D case through both. |
| How large is the sign-split error vs true q/d for dodecane at flame conditions? | Standalone CPU harness: call `comp_qfqr` + stoichiometric q/d vs sign-split of `RTY2WDOT` at T=800–2500 K, φ=0.7, p=10 atm; print τᵢ for OH, H, O. |
| Is forcing or chemistry the dominant error in your counterflow case? | Run with `rYsrc=0` artificially zeroed in a patched `odefun` in cold zone vs flame zone; compare to full forcing. |
| Does T sign-split matter once species q/d are fixed? | After Fix 1+2, toggle T sign-split vs net `Tdot`; compare 0D ignition and 2D counterflow profiles. |
| Are failures from `dt < dtmin` widespread? | Enable `qss.verbose=1`, count `"integration failed for cell"` messages; histogram `FCunt` values. |
| GPU build path? | Confirm build is CPU-only for QSS; if `AMREX_USE_GPU=1`, you're hitting the abort at `ReactorQSS.cpp:313`. |

---

## 7. Bonus — standalone repro sketch (Task 7)

```cpp
// main_qss_qd_compare.cpp — CPU-only sketch, no AMReX
#include "mechanism.H"
#include <cmath>
#include <iostream>

static void sign_split_qd(const amrex::Real wdot[], amrex::Real q[], amrex::Real d[], int n) {
  for (int i = 0; i < n; ++i) { q[i] = std::max(0., wdot[i]); d[i] = std::max(0., -wdot[i]); }
}

static void true_qd_from_qfqr(
  const amrex::Real qf[], const amrex::Real qr[], amrex::Real q[], amrex::Real d[])
{
  for (int i = 0; i < NUM_SPECIES; ++i) { q[i] = 0.; d[i] = 0.; }
  for (int rxn = 0; rxn < NUM_GAS_REACTIONS; ++rxn) {
    int ns, kI[4], nu[4];
    CKINU(rxn, ns, kI, nu);
    for (int j = 0; j < ns; ++j) {
      int sp = kI[j] - 1; // CK convention: 1-based
      if (nu[j] < 0) { d[sp] += (-nu[j]) * qf[rxn]; q[sp] += (-nu[j]) * qr[rxn]; }
      else           { q[sp] +=  nu[j]  * qf[rxn]; d[sp] +=  nu[j]  * qr[rxn]; }
    }
  }
  for (int i = 0; i < NUM_SPECIES; ++i) { q[i] *= mw(i); d[i] *= mw(i); } // mol/s -> g/cm³/s
}

int main() {
  const amrex::Real T = 800.0;
  const amrex::Real rho = 5.0e-4; // g/cm³ ~ 10 atm air-ish
  amrex::Real Y[NUM_SPECIES] = {0.0};
  Y[NC12H26_ID] = 0.01; Y[O2_ID] = 0.21; Y[N2_ID] = 0.78;

  amrex::Real c[NUM_SPECIES], wdot[NUM_SPECIES], q_net[NUM_SPECIES], d_net[NUM_SPECIES];
  amrex::Real q_true[NUM_SPECIES], d_true[NUM_SPECIES];
  amrex::Real qf[NUM_GAS_REACTIONS], qr[NUM_GAS_REACTIONS];

  CKYTCR(rho, T, Y, c);
  CKWC(T, c, wdot);
  sign_split_qd(wdot, q_net, d_net, NUM_SPECIES);

  amrex::Real sc_qss[18] = {0};
  comp_qfqr(qf, qr, c, sc_qss, T, 1./T, log(T));
  true_qd_from_qfqr(qf, qr, q_true, d_true);

  const int keys[] = {OH_ID,O_ID,H_ID,HO2_ID,H2O_ID,H2_ID,O2_ID,N2_ID};
  for (int sp : keys) {
    amrex::Real tau_net  = d_net[sp]  / std::max(rho*Y[sp], 1.e-30);
    amrex::Real tau_true = d_true[sp] / std::max(rho*Y[sp], 1.e-30);
    std::cout << sp << " wdot=" << wdot[sp]
              << " q_net=" << q_net[sp] << " d_net=" << d_net[sp] << " tau_net=" << tau_net
              << " | q_true=" << q_true[sp] << " d_true=" << d_true[sp] << " tau_true=" << tau_true
              << "\n";
  }
}
```

Expect orders-of-magnitude τ discrepancy for H, O, OH in stiff conditions when `q_true ≈ d_true >> |ω̇|`.

---

## 8. Summary

The port is **not** a units or interface wiring problem — flatten/unflatten, `ρY` state, `reactor_type` branching, and forcing array plumbing match RK64/Cvode. The defect is **algorithmic**: α-QSS requires true separated creation/destruction rates, but the Pele port reconstructs them from net ω̇ (and net ω̇ + forcing) via `max(0,·)`. CEPTR already generates the needed per-reaction `qf`/`qr` (`comp_qfqr`, `CKKFKR`); the QSS reactor simply never uses them.

**Recommended next step:** Fix 1 (true q/d from `comp_qfqr`) + Fix 2 (explicit forcing decoupling).

---

## Key file references

| File | Role |
|------|------|
| `PelePhysics/Source/Reactions/ReactorQSS.cpp` | QSS reactor; `odefun` sign-split bug |
| `PelePhysics/Source/Reactions/ReactorQSS.H` | Documents sign-split design |
| `PelePhysics/Source/Reactions/qss_int.cpp` | CHEMEQ2 integrator core |
| `PelePhysics/Source/Reactions/ReactorUtils.H` | `fKernelSpec`, `box_flatten`/`box_unflatten` |
| `PelePhysics/Source/Reactions/ReactorRK64.cpp` | Gold-standard explicit reactor |
| `PelePhysics/Mechanisms/dodecane_lu_qss/mechanism.H` | `productionRate`, `comp_qfqr` |
| `PelePhysics/Mechanisms/dodecane_lu_qss/mechanism.cpp` | `CKKFKR`, `progressRateFR` |
| `PeleLMeX/Exec/Production/CounterFlow_ndodecane/inputs/input.qss` | Example QSS run inputs |

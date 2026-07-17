# QSS Parity Ladder (Pele vs Cantera / Python reference)

Debugging must not validate fixes inside the confounded Pele driver alone.
Each step gates the next.

## Step 0 — Pin one case (never vary during debugging)

| Parameter | Value | Notes |
|-----------|-------|-------|
| T₀ | 800 K | Paper Table 2 |
| P | 10 atm (1.01325×10⁶ Pa) | |
| Mixture | Z = 0.062 | Set via Cantera composition; map to `hr.equiv_ratio` or extend init |
| Outer step | `ode.dt = 1e-6` s | Same 1 µs window as Cantera/Ember/RL training |
| End time | ~5 ms (`ode.ndt = 5000`) | Covers ~2.29 ms ignition delay + margin |
| Mechanism | `dodecane_lu` | 53 species / 268 rxns in Pele — **verify vs paper 106-species Luo** |

Inputs template: `PelePhysics/Testing/Exec/IgnitionDelay/inputs/inputs.0d_paper`

**Success criterion for trajectory step:** Pele-QSS matches **your Cantera-QSS** trajectory (including known QSS flaws), not CVODE.

---

## Step 1 — Rate parity (standalone, no Pele driver)

**Goal:** `progressRateFR` + `CKINU` assembly net equals `RTY2WDOT` / Cantera ω̇ at fixed (T, Y, P).

**Do not use** `align_species_qd_to_wdot()` — if nets disagree, root-cause units, indexing, third-body, or assembly.

### Cantera side
```bash
cd PelePhysics/Testing/Exec/IgnitionDelay
python3 rate_parity_cantera.py \
  --mech ../../Mechanisms/dodecane_lu/mechanism.yaml \
  --T 800 --P 1013250
```

Pull 3–5 states from a Cantera QSS trajectory; compare per-reaction `forward_rates_of_progress` / `reverse_rates_of_progress`.

### Pele side
- Enable `qss.qd_check = 1` once per run (logs mismatches vs `RTY2WDOT`)
- Optional: standalone C++ harness calling `progressRateFR` + stoichiometry (see `qss_diagnosis_report.md` Fix sketch)

**Gate:** max relative net-rate error < 1e-6 at all test states → proceed. Else fix assembly before touching integrator.

---

## Step 2 — Single-step parity (formula-level)

**Goal:** One 1 µs α-QSS step from identical (T, Y, P): C++ `qss_int.cpp` + `odefun` vs Python reference.

**Isolate:** α(τ), predictor, corrector, convergence — no flatten/unflatten, no outer driver.

**Gate:** |ΔT| and max |ΔYᵢ| < tolerance vs Python → proceed.

---

## Step 3 — Trajectory parity in Pele

**Goal:** Full run with pinned case, stock energy recovery, 1 µs outer steps.

```bash
make -j4 USE_MPI=FALSE
./Pele2d.gnu.ex inputs/inputs.0d_paper > LOG_paper_qss.log 2>&1
```

### Diagnostics (enabled in paper inputs)
| Flag | Output |
|------|--------|
| `qss.qd_check = 1` | One-time q/d vs `RTY2WDOT` at first odefun |
| `qss.energy_consistency = 1` | `\|T_integrated − T_recovered\|` per outer step |
| `ode.verbose = 1` | Outer step start/done only |

**Gate:**
- `|T_int − T_rec| < 1 K` when chemistry is consistent (primary scalar)
- PPreaction matches Cantera-QSS trajectory shape (not CVODE)

---

## Removed / reverted (course correction)

| Change | Status | Reason |
|--------|--------|--------|
| `align_species_qd_to_wdot()` | **Deleted** | Rescales τᵢ; masks progressRateFR vs productionRate bug |
| `qss_box_unflatten()` keep T | **Reverted** | Silenced energy inconsistency; use stock `box_unflatten` |
| `qss_box_flatten()` trust T | **Reverted** | Use stock `box_flatten` (T from energy) |
| `ode.dt = 0.02` s | **Wrong for parity** | 20 ms outer step ≠ 1 µs RL/Cantera window |

---

## Mechanism check

Before Step 3: confirm `dodecane_lu` (53 sp) vs paper Luo (106 sp). If different, export Pele YAML and run Python QSS on **that** mechanism for comparison.

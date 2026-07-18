# Design decisions log

| Date | Decision | Justification |
|------|----------|---------------|
| 2026-07-15 | Use ESI OpenFOAM **v2312** (not Foundation OF11) | Spec requires templated `StandardChemistryModel` / `chemistrySolver` hierarchy and DLBFoam compatibility |
| 2026-07-15 | Develop on Mac via Docker bind-mount | OpenCFD images are linux/amd64; Mac runs under Docker Desktop emulation |
| 2026-07-15 | Mechanism from `handoff` packaged `n-dodecane.yaml` | Single source of truth matching 0D eval; avoid Pele Lu-53 |
| 2026-07-15 | Policy from `best_offline_eval2.pt` | Production CnF / handoff paper checkpoint (19-D) |
| 2026-07-15 | Port CHEMEQ2 from Pele `qss_int` (std::vector, no AMReX) | Algorithm already patched for true q/d; integrate into ESI chemistrySolver |
| 2026-07-15 | Chemistry integrates const-P composition + T from energy in cell ODE; OF couples via effective RR | Match 0D training (const-P) as closely as ESI RR interface allows; log T-consistency diagnostic |
| 2026-07-15 | `maxChemDeltaT=1e-6`, policy every 20 sub-windows | Match handoff `num_steps=20` at `dt=1e-6` |
| 2026-07-15 | LibTorch CPU for batched policy inference | Matches paper CPU inference; avoid GPU under MPI complexity on workstation |
| 2026-07-15 | chemkinToFoam needs OF `transportProperties` dict (not Chemkin tran.dat) | ESI tutorial / Allrun convention; Cantera `tran.dat` rejected by Foam lexer |
| 2026-07-15 | Rewrite Cantera thermo → 80-col CHEMKIN-II (`therm_of.dat`) | Cantera headers (`G300.000`) break OpenFOAM chemkinReader |
| 2026-07-15 | ELEMENTS one-per-line; `REACTIONS CAL/MOLE` only | Fixes ESI chemkinLexer parse of yaml2ck output |
| 2026-07-15 | Docker `--entrypoint /bin/bash` | Image entrypoint `/openfoam/run` breaks nested bash quoting |
| 2026-07-15 | MidT Python QSS slower than CVODE in one spot-check | Binding/config overhead possible; keep profiling gate when OF port is timed |
| 2026-07-17 | E10b CLOSED: GRI near-uniform (50/53); Luo 28 Tcommons; severity GRI~0% vs Luo −681% at burnt Y | Human ack → Option R; species[0]=h (Tcommon=5000) amplifies Luo crash band |
| 2026-07-17 | **Option R ships** (relaxed fidelity gates 0.5% cp / 4 kJ/kg) | Add-ons PASS: equil \|ΔT\|≤0.008 K, \|ΔY_major\|≤3e-7; 4-miss effect-size mix-rel ≤1.1e-5 ≪1e-4; kinetic Δτ_max=0.016%; blend identity 0% on refit foam. Production = refit thermo + stock THE; massWeighted* → diagnostics/ after E11.3 green |

---

## E11 Option R — evidence package (2026-07-17)

### Relaxed fidelity gates
- Per-species vs original polys on [300, 3000]: max\|Δcp\|/cp ≤ **0.5%**, max\|Δhs\| ≤ **4 kJ/kg** (was 0.2% / 2 kJ/kg).
- Selected refit: shared **[300, 1000, 3500]** (Tc=1000 beats Tc=1400 on worst-species cp).

### Equilibrium invariance (add-on 1) — PASS
HP equilibrate, original vs refit, Z∈[0.02,0.12] × p∈{10,30,60} atm:

| metric | value | gate |
|--------|------:|------|
| max\|ΔT_equil\| | **0.0079 K** | ≤1 K |
| max\|ΔY_major\| | **2.9e-7** | ≤1e-5 |

### Effect-size of 4 strict-gate misses (add-on 2) — PASS
Peak Yi along MidT × property error → mixture-relative contribution (expected ≤1e-4):

| species | peak Y | max mix-rel cp | max mix-rel hs |
|---------|-------:|---------------:|---------------:|
| c8h17coch2 | 3.9e-7 | 1.5e-9 | 4.9e-11 |
| c3h4-a | 1.3e-4 | 8.5e-7 | 4.2e-8 |
| oh | 6.6e-3 | **1.1e-5** | 1.4e-6 |
| c2h6 | 7.7e-4 | 3.6e-6 | 4.0e-7 |

### Kinetic invariance — PASS
max\|Δτ_ign\|=0.016% on T0×p grid (gate 0.5%).

### Severity (E10b) — why GRI survived / Luo died

| Mech | species[0] Tcommon_mix | T=2000 burnt Δcp |
|------|------------------------|-----------------:|
| GRI | CH4 / 1000 K | ~0% |
| Luo original | **h / 5000 K** | **−151%** (sign flip) |
| Luo refit | h / **1000 K** | **0.0000%** |

`janafThermo::operator+=` keeps Tcommon from species[0]; debug-mode only FATAL on mismatch. Luo `h` single-range Tcommon=5000 forced the mixture onto blended *low* coeffs through the 1700–1850 K crash band.

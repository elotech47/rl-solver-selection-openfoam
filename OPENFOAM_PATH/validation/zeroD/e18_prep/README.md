# E18-prep — cold-flow → chemistry restart (twin-nozzle counterflow)

**Status:** Stage 0 COMPLETE · Stage 1 COMPLETE · Stage 2 in progress

## Stage 0 — ignition viability (DONE)

See `stage0_scout/STAGE0_REPORT.md`.

| Pick | Value |
|------|-------|
| **p** | **10 atm** (not 1 atm) |
| **T_air** | **1000 K** |
| **strain a** | **100 s⁻¹** |
| τ_ign (MRM hot) | ≈ 1.42 ms |
| Z\* / Tmix\* | ≈ 0.12 / ≈ 830 K |

## Stage 1 — cold mixing (DONE)

See `stage1_cold/STAGE1_REPORT.md`.

| Quantity | Value |
|----------|-------|
| Gap L | **0.008 m** (Ember `example_diffusion` match; **not** E17’s 0.02 m) |
| V_inlet | **±0.4 m/s** = a·L/2 |
| Mesh | 20k (200×100), mid-plane refined |
| Chemistry | OFF — Tmax = **1000.000 K** (PASS) |
| Freeze | **t = 0.05 s** (~2.5 τ_flow) |
| Stagnation (Ux=0) | x ≈ **0.00622 m** (air side of geometric midplane 0.004 m) |
| Ignition readiness | 37 cells with \|Z−0.12\|<0.02; best Z≈0.118, T≈811 K |
| alphaEff | **PASS** μ≈2–4.5e−5, α_eff≈2.5–6.5e−5, 20000/20000 cells |

**alphaEff root cause:** Sutherland `As=Ts=0` in thermo → μ≡κ≡α≡0. Patched to air-like As=1.67212e−6, Ts=170.672.

## Stage 2 — chemistry restart (NEXT)

- Restart frozen IC → cvodeOnly / qssOnly / rlAdaptive
- Guards ON; matched writeInterval; endTime = freeze + ~9 ms
- Scripts: `stage2_chem_restart.sh`, `stage2_run_one.sh`

## Files

| Path | Role |
|------|------|
| `stage0_scout/` | Viability scout |
| `stage1_cold/` | Cold mixing + reports |
| `cases/opposedJet_E18/` | Production case (freeze at 0.05) |
| `OPENFOAM_PATH/DECISIONS.md` | Geometry + alphaEff decisions |

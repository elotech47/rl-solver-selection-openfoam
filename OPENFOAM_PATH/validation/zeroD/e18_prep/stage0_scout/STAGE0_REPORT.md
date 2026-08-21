# E18 Stage 0 — Ignition viability scout

**Method:** Mixing-line most-reactive mixture (MRM) 0D const-p ignition delay vs opposed-jet residence τ_res=1/a. Comfortable: τ_ign/τ_res ≤ 0.5. Not a full transient 1D counterflow ODE; optional steady CF checks separate.
**Mechanism:** `n-dodecane_refit.yaml`

## Production pick

| quantity | value |
|----------|-------|
| p | **10.0 atm** |
| T_air | **1000.0 K** |
| strain a | **100.0 s⁻¹** |
| τ_ign (MRM) | 1.42 ms |
| τ_res = 1/a | 10.00 ms |
| τ_ign / τ_res | 0.142 |
| Z\* | 0.12 |
| Tmix\* | 830.5 K |
| T_peak 0D | 2128.2 K |
| ignition side (mix) | near-stoich/fuel-rich |

**Hot-ignition criterion:** τ counted at T ≥ max(T₀+800, 1800) K (NTC/cool-flame bumps discarded).

## Rationale

- Production pick: p=10.0 atm, T_air=1000.0 K, a=100.0 s⁻¹, τ_ign=1.42 ms, τ_res=1/a=10.00 ms, Da⁻¹=τ·a=0.142, Z*=0.12, Tmix*=830.5 K.
- p=10 atm retained: matches OF/E12–E17 mechanism validation pressure and yields comfortable ignition at moderate strain; 1 atm only if scout requires.
- Inlet velocities for 2D: a ≈ 2·V_inlet/gap (equal-momentum); with gap L, V_inlet ≈ a·L/2.

## Ignition / no-ignition boundary (min T_air by class)

### p = 1.0 atm
| a [1/s] | min T comfortable | min T marginal | min T ignites |
|--------:|------------------:|---------------:|--------------:|
| 50 | 1200.0 | 1200.0 | 1000.0 |
| 100 | 1200.0 | 1200.0 | 1000.0 |
| 200 | None | 1200.0 | 1000.0 |
| 400 | None | None | 1000.0 |
| 800 | None | None | 1000.0 |

### p = 10.0 atm
| a [1/s] | min T comfortable | min T marginal | min T ignites |
|--------:|------------------:|---------------:|--------------:|
| 50 | 1000.0 | 1000.0 | 1000.0 |
| 100 | 1000.0 | 1000.0 | 1000.0 |
| 200 | 1000.0 | 1000.0 | 1000.0 |
| 400 | 1200.0 | 1000.0 | 1000.0 |
| 800 | None | 1200.0 | 1000.0 |

## Files

- `scout_grid.csv` — flat results
- `scout_grid_full.json` — includes Z scans
- `ignition_map_p*.png` — (a, T_air) maps

## Next (Stage 1) — not built yet

Twin-nozzle cold mixing at pick (a, T_air, p); chemistry OFF; freeze developed field.
## 2D velocity sizing (Stage 1)

For gap L=0.02 m (current opposedJet box): V_inlet ≈ a·L/2 = **1.0 m/s** at a=100 s⁻¹.

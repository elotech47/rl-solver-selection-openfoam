# E15 equilibration audit — 800/10/1.5 and 1000/10/0.5

Criterion: settled if |ΔT| over last 5% of endTime < 2 K and T-range < 5 K.

If non-settled: would rerun both frameworks at 3–5× τ_main. If settled: anomaly is real — **no fix**.

## T800_p10_phi1p5 (T=800, p=10, φ=1.5)

- endTime / τ_main ≈ **1.75×** (map used 2× Cantera-presized τ)
- OF-QSS: T_end=2415.0 K, last-5% ΔT=0.200 K, range=0.400 K, median |dT/dt|=2.38e-07 → **SETTLED**
- OF-CVODE: T_end=1994.7 K, last-5% ΔT=0.000 K → **SETTLED**
- OF ΔTeq (QSS−CVODE) = **420.2 K**; Py ΔTeq = **36.9 K**
- **Action:** report real anomaly no fix

## T1000_p10_phi0p5 (T=1000, p=10, φ=0.5)

- endTime / τ_main ≈ **1.93×** (map used 2× Cantera-presized τ)
- OF-QSS: T_end=2105.7 K, last-5% ΔT=0.000 K, range=0.000 K, median |dT/dt|=1.19e-07 → **SETTLED**
- OF-CVODE: T_end=2159.5 K, last-5% ΔT=0.000 K → **SETTLED**
- OF ΔTeq (QSS−CVODE) = **-53.8 K**; Py ΔTeq = **6.9 K**
- **Action:** report real anomaly no fix

## Verdict

Both conditions are **settled** at map endTime. The large OF–Py ΔTeq mismatches are **real residual anomalies**, not truncated equilibration. No extended rerun; **no code fix** (per close-out directive).

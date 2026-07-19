# Frozen rung (b)/(c) acceptance — CONFORM baseline v1

**Date:** 2026-07-19  
**Tag:** `validation-baseline-v1` (alias `e15-conform-baseline-v1`)  
**Build:** OF-QSS corrector T-freeze ON, `epsmin=0.02`

## Rung (b) — single 1 µs step (MidT hard case 800 K / 10 atm / φ=1 ≈ Z≈0.062)

IC: `of_ics/T800_p10_phi1p0_initialConditions`. OF harness: `e15_rung_b_midt_host.sh`.

| Solver | T₀ [K] | T₁ [K] | ΔT [K] |
|--------|-------:|-------:|-------:|
| Py-CVODE | 800.0000 | 800.0000 | -3.0504e-09 |
| Py-QSS (T-freeze ODE) | 800.0000 | 800.0000 | -6.8510e-09 |
| OF-CVODE | 800.0000 | 800.0000 | 0.0000e+00 |
| OF-QSS (Tfreeze) | 800.0000 | 800.0000 | 0.0000e+00 |

Accept (spec): OF-QSS vs Py-QSS at float noise; OF-CVODE vs Py-CVODE within tol.
At MidT IC the 1 µs ΔT is ~0 on all instruments (pre-ignition).
Envelope evidence that T-freeze closes the OF–Py gap is in the 38-condition map.

## Rung (c) — 0D trajectories (conform map)

| Case | τ_OF-QSS [ms] | τ_Py-QSS [ms] | OF/Py | τ_OF-CVODE [ms] | τ_Py-CVODE [ms] | OF-C/Py-C | ΔTeq OF | ΔTeq Py |
|------|--------------:|--------------:|------:|----------------:|----------------:|----------:|--------:|--------:|
| NTC_lowT | 5.55 | 5.689 | 0.9756 | 5.308 | 5.355 | 0.9913 | -2e+01 | -3e+01 |
| MidT_MidP | 2.387 | 2.409 | 0.991 | 2.24 | 2.263 | 0.9897 | -1e+01 | 2e+01 |
| high_T0 | 4.959 | 4.956 | 1.001 | 4.741 | 4.745 | 0.9992 | -4 | 2e+01 |
| HighT_HighP | 1.525 | 1.509 | 1.011 | 1.23 | 1.237 | 0.9946 | 2e+01 | 3 |
| timeout_cleared | 3.666 | 3.705 | 0.9895 | 3.602 | 3.628 | 0.9929 | -5e+01 | -3e+01 |

### Spec gates (instruction §3.4) — recorded under conform

- OF-CVODE vs Py-CVODE MidT: **-1.03%** (accept ≤1%: CHECK)
- OF-QSS vs Py-QSS MidT: **-0.90%** (accept ≤1% vs Cantera-QSS: PASS)
- OF-QSS vs Py-CVODE MidT: **5.5%** (characteristic QSS bias; not a defect if OF≈Py QSS)

## Verdict

This file is the **frozen 0D validation table** for thesis citation under
`validation-baseline-v1`. Production QSS = T-freeze + epsmin=0.02.
Full envelope: `FROZEN_VALIDATION_BASELINE_v1.md`, maps under `e15_conformance/`.


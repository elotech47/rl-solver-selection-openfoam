# Frozen validation baseline v1 — OF-QSS CONFORM (T-freeze)

**Tag:** `validation-baseline-v1` → commit `823b1c2`  
**Alias:** `e15-conform-baseline-v1` (same commit; prefer the canonical name in thesis citations)  
**Date:** 2026-07-19  
**Config:** production QSS = corrector T-freeze ON, `epsmin=0.02` (see DECISIONS.md)

## Conform qssCoeffs (verbatim)

```
qssCoeffs
{
    epsmin          0.02;
    epsmax          100;
    dtmin           1e-12;
    dtmax           1e-06;
    abstol          1e-11;
    itermax         2;
    Tfreeze         true;  // predictor: thermo at T=y[0]; corrector: freeze T/rho/cp/ha
}
```

T-freeze semantics (handoff `CanteraQSSODE`): predictor evaluates rates/thermo at
current T and caches T, ρ, cp, ha; corrector re-evaluates rates at frozen T with
updated composition, using cached thermo. CVODE path untouched.

## Envelope map (38 conditions)

- OF-QSS failures cleared: map complete; ΔTeq holes remaining: **0**
- ΔTeq sign match vs Py: **30** (was 15 pre-freeze)
- Artifacts: `E15_SIGNATURE_MAP_OF.md`, `E15_OF_VS_PY_DIFFS.md`,
  `E15_BEFORE_AFTER_TFREEZE.md`, `e15_drift_vs_dTeq.png`

## Equilibration audit (anomalies)

800/10/φ=1.5 and 1000/10/φ=0.5: both **settled** at map endTime; OF–Py ΔTeq
mismatches are **real residuals** (no fix). See `E15_EQUILIBRATION_AUDIT.md`.

## Rung (c) — 0D trajectory acceptance (conform build)

Ignition marker: τ_main = argmax(dT/dt). Accept vs Py-QSS: τ within few %;
ΔTeq sign family preferred (envelope evidence, not per-point hard gate).

| T0 | p | φ | τ_OF [ms] | τ_Py [ms] | τ OF/Py | ΔTeq OF | ΔTeq Py |
|---:|--:|--:|----------:|----------:|--------:|--------:|--------:|
| 700 | 10 | 1.0 | 5.69 | 5.78 | 0.985 | -4e+01 | -1e+01 |
| 700 | 30 | 1.0 | 4.09 | 4.14 | 0.987 | -4e+01 | -4e+01 |
| 700 | 60 | 1.0 | 3.67 | 3.71 | 0.989 | -5e+01 | -3e+01 |
| 800 | 10 | 1.0 | 2.39 | 2.41 | 0.991 | -1e+01 | 2e+01 |
| 800 | 30 | 1.0 | 0.858 | 0.89 | 0.964 | -4e+01 | -1e+01 |
| 800 | 60 | 1.0 | 0.61 | 0.631 | 0.967 | -2 | -3e+01 |
| 1000 | 10 | 1.0 | 4.96 | 4.96 | 1 | -4 | 2e+01 |
| 1000 | 30 | 1.0 | 1.53 | 1.51 | 1.01 | 2e+01 | 3 |
| 1000 | 60 | 1.0 | 0.677 | 0.665 | 1.02 | -2e+01 | 2e+01 |

### MidT_MidP anchor (800 K / 10 atm / φ=1 ≈ Z=0.062)

| Instrument | τ_main [ms] | vs Py-CVODE |
|------------|------------:|------------:|
| Py-CVODE | 2.26 | — |
| Py-QSS | 2.41 | 6% |
| OF-CVODE | 2.24 | -1% |
| OF-QSS (conform) | 2.39 | 5% |
| OF-QSS vs Py-QSS | — | -0.9% |

## Rung (b)/(c) — frozen 0D validation table (thesis citation)

**Artifact:** `FROZEN_RUNG_BC_ACCEPTANCE.md` (+ `frozen_rung_bc_acceptance.json`).

Rung (b): MidT 800 K / 10 atm / φ=1, single 1 µs step under conform (`Tfreeze true`).  
Rung (c): selected envelope trajectories from the T-freeze 38-map.

## 2D QSS

**UNBLOCKED** for opposed-jet qssOnly + rlAdaptive smoke (master spec §5.2).
See `DEBUG_REPORT.md`.


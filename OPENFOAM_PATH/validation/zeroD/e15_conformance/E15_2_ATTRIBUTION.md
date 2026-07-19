# E15.2 Attribution table

Per-knob full-trajectory toggles at NTC_lowT → MidT → high_T0.
All **21/21** runs `failure=ok`.

Success criterion (conform): OF-QSS matches Py-QSS τ (few %), ΔTeq sign+magnitude family,
drift ~1×; optionally clears map timeouts.

## Headline

**Coefficient toggles alone do not conform.** NTC is where the frameworks disagree most, and
no E15.1 coeff knob restores Py-QSS’s **negative** ΔTeq / opposite-signed ΔZ fingerprint.

| Knob | Effect |
|------|--------|
| `epsmax→20`, `dtmin→1e-15` | **No-ops** (bit-identical to baseline at all 3 points) |
| `epsmin→0.01` | Mild help at NTC (ΔTeq +80→+52 K) and MidT drift reshuffle; **not** Py-family |
| `abstol→1e-8`, `conform_coeffs` | **Worse** MidT (ΔTeq +15→+40…+60 K, drift up) |

→ Residual gap is in **T-freeze / energy odefun / suggestDeltaT controller** (code-level),
not the scalar qssCoeffs table.

## NTC_lowT (T=700, p=60, φ=0.5) — decisive

| toggle            | τ_main [ms] | Teq   | ΔTeq vs CVODE | ΔZ_C        | ΔZ_H        | ΔZ_O        |
| -------------------| ------------:| ------:| --------------:| ------------:| ------------:| ------------:|
| baseline          | 4.88        | ~1926 | **+80**       | +2.0e-3     | +3.7e-4     | ~0          |
| epsmin_0p01       | 5.02        |       | **+52**       | +1.3e-3     | +2.4e-4     | +5e-5       |
| epsmax_20 / dtmin | = baseline  |       | +80           |             |             |             |
| abstol_1e-8       | 4.62        |       | **+148**      | +3.7e-3     |             |             |
| conform_coeffs    | 4.76        |       | **+113**      | +2.8e-3     |             |             |
| cvode_ref         | 5.31        |       | 0             | ~0          | ~0          | ~0          |
| **Py-QSS**        | **5.69**    |       | **−32**       | **−7.9e-4** | **−1.4e-4** | **+7.1e-4** |

OF vs Py at NTC: **ΔTeq sign flip**, **ΔZ_C/H sign flip**, τ_main ~14% early. Coeffs cannot fix.

## MidT (T=800, p=10, φ=1.0)

| toggle                  | τ_main [ms] | ΔTeq vs CVODE | notes                                        |
| -------------------------| ------------:| --------------:| ----------------------------------------------|
| baseline                | 1.98        | +15           | closest to Py ΔTeq ~+16 among OF toggles     |
| epsmin_0p01             | 2.13        | +20           | τ closer to Py (2.41); drift pattern changes |
| abstol / conform_coeffs | 1.71 / 1.65 | +40 / +60     | regress                                      |
| Py-QSS                  | 2.41        | +16           |                                              |

## high_T0 (T=1000, p=10, φ=1.0)

Already near Py on τ (~4.95 vs 4.96) and ΔTeq (~+17–20). Coeff toggles ≈ no change.
`epsmin_0p01` drops ΔTeq to **−2 K** and shrinks ΔZ_O — interesting but NTC still broken.

## Conform-config candidate

**No scalar-coeff candidate meets the success criterion.**

Provisional next candidate for E15.2b (code rebuild):

1. **T-freeze on QSS corrector** (E15.1 major row — handoff yes / OF no)
2. Optionally handoff-like `epsmin=0.01` *after* T-freeze, not before
3. Re-test timeout points (T700/T900 @ 60 atm φ=1 QSS) under that build

Auto-rank by weak score picked `epsmax_20` (= baseline) — **ignore**; NTC score was 0 for all.

## Artifacts

- Full table: this file / `e15_2_attribution_table.json` / `e15_2_raw.json`
- Runs: `e15_2_runs/`

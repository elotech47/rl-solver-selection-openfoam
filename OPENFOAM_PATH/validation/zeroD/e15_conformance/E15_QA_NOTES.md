# E15 QA notes

## (1) τ_first missing on OF — not undersampling
`chemFoam.out` writes **every outer step** (`output.H`); MidT/NTC traces have
median Δt = **1.0 µs**. Field `writeInterval = endTime` only affects VTK/Y dumps.

Prior marker used `min_frac_of_main_peak=0.15`. OF first-stage peaks are typically
**7–9%** of the main `dT/dt` peak → all rejected. Retune:

- `min_frac_of_main_peak = 0.06`
- require `t < 0.8 × τ_main`
- require a **valley** between first and main (`g_lo ≤ 0.45 × min(peaks)`)

After retune, OF recovers τ_first on the same NTC lean family as Python
(700–800 K, φ=0.5, elevated p).

## (2) Timeout Teq=3500 leakage
QSS timeouts clamped to JANAF Thigh. QA: if `failure≠ok` or `Teq≥3490`, set
`Teq/ΔTeq/drift = N/A` but keep the row.

## (3) 1000 K / 1 atm CVODE timeouts
Both φ=1.0 and φ=1.5: CVODE `wall_timeout`, QSS `ok`.
Paired ΔTeq baseline is explicitly **`UNAVAILABLE(cvode_failure=wall_timeout)`** —
do not interpret QSS Teq − (missing CVODE) as ΔTeq.
Rerun: `validation/zeroD/e15_rerun_cvode_1000_1.sh` with wall cap **3600 s**.

## (4) Signed per-element drift
Maps now report **ΔZ_C, ΔZ_H, ΔZ_O** (endpoint vs IC). Use these for E15.2
fingerprint matching against E15.1 config diffs (φ-dependent OF/Py sign flips).

## (5) 1000/60/φ=1.0 “Δτ≈2×”
Under old markers, QSS reported a spurious τ_first on the first of two heat-release
humps. Retuned markers clear τ_first. Remaining fact:

| solver | τ_main [ms] | peak structure |
|--------|------------:|----------------|
| CVODE | 0.416 | single peak @ T≈2223 K |
| QSS | 0.831 | peaks @ 0.665 (59% gmax, T≈2226) and 0.831 (gmax, T≈2504) |

So the ~2× τ_main ratio is a **real QSS double-hump / delayed global max**, not a
cool-flame labeling bug. Track in E15.2 high_T0 toggles.

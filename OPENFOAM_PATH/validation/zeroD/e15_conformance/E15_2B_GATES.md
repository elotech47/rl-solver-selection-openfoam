# E15.2b — T-freeze alone (epsmin=0.02)

**Overall: GATES RED**

One change: corrector T-freeze (handoff CanteraQSSODE). `epsmin=0.01` held back.

## NTC_lowT (T=700, p=60, φ=0.5)

| toggle | τ_main [ms] | Teq | ΔTeq vs CVODE | ΔZ_C | ΔZ_H | ΔZ_O | wall [s] | fail |
|--------|------------:|----:|-------------:|-----:|-----:|-----:|---------:|------|
| Tfreeze_on | 5.55 | 2e+03 | -2e+01 | -0.000623 | -0.000115 | 0.000669 | 2e+01 | ok |
| Tfreeze_off | 4.88 | 2e+03 | 8e+01 | 0.00202 | 0.000373 | 6.34e-06 | 3e+01 | ok |
| cvode_ref | 5.31 | 2e+03 | 0 | 9.02e-07 | 1.68e-07 | 7.6e-06 | 1e+02 | ok |

Py-QSS: τ_main=5.69 ms, ΔTeq=-3e+01 K, ΔZ_C=-0.000787, ΔZ_H=-0.000143, ΔZ_O=0.000709, wall=1.5 s

**Gate (NTC_lowT):** PASS — `{"tau_within_few_pct": true, "tau_err": 0.024394445421061728, "late_signed_vs_cvode": true, "dteq_sign": true, "ntc_negative": true, "dteq_mag_family": true, "dteq_mag_loose": true, "of_dteq": -23.75, "py_dteq": -32.08785063437722, "dz_signs": true, "dz_mag_1x": true, "high_T0_no_regress": true, "cvode_Teq_vs_e152": 0.0, "cvode_unchanged": true}`

## MidT (T=800, p=10, φ=1.0)

| toggle | τ_main [ms] | Teq | ΔTeq vs CVODE | ΔZ_C | ΔZ_H | ΔZ_O | wall [s] | fail |
|--------|------------:|----:|-------------:|-----:|-----:|-----:|---------:|------|
| Tfreeze_on | 2.39 | 3e+03 | -1e+01 | -0.00106 | 2.91e-05 | 0.00222 | 1e+01 | ok |
| Tfreeze_off | 1.98 | 3e+03 | 1e+01 | 0.00304 | 0.00064 | -0.000937 | 1e+01 | ok |
| cvode_ref | 2.24 | 3e+03 | 0 | 0.000861 | 0.000124 | 1.59e-05 | 5e+01 | ok |

Py-QSS: τ_main=2.41 ms, ΔTeq=2e+01 K, ΔZ_C=-0.000774, ΔZ_H=-0.000161, ΔZ_O=0.00015, wall=1.2 s

**Gate (MidT):** FAIL — `{"tau_within_few_pct": true, "tau_err": 0.008995433789952378, "late_signed_vs_cvode": true, "dteq_sign": false, "ntc_negative": true, "dteq_mag_family": true, "dteq_mag_loose": true, "of_dteq": -10.480000000000018, "py_dteq": 15.87834435669356, "dz_signs": false, "dz_mag_1x": false, "high_T0_no_regress": true, "cvode_Teq_vs_e152": 0.0, "cvode_unchanged": true}`

## high_T0 (T=1000, p=10, φ=1.0)

| toggle | τ_main [ms] | Teq | ΔTeq vs CVODE | ΔZ_C | ΔZ_H | ΔZ_O | wall [s] | fail |
|--------|------------:|----:|-------------:|-----:|-----:|-----:|---------:|------|
| Tfreeze_on | 4.96 | 3e+03 | -4 | -7.27e-05 | 0.000135 | 0.000199 | 3e+01 | ok |
| Tfreeze_off | 4.95 | 3e+03 | 2e+01 | -4.66e-05 | 0.000631 | 0.00399 | 3e+01 | ok |
| cvode_ref | 4.74 | 3e+03 | 0 | 0.000648 | 9.33e-05 | 1.34e-05 | 1e+02 | ok |

Py-QSS: τ_main=4.96 ms, ΔTeq=2e+01 K, ΔZ_C=-0.000317, ΔZ_H=0.00049, ΔZ_O=0.00425, wall=1.8 s

**Gate (high_T0):** FAIL — `{"tau_within_few_pct": true, "tau_err": 0.0006719128328624979, "late_signed_vs_cvode": true, "dteq_sign": false, "ntc_negative": true, "dteq_mag_family": false, "dteq_mag_loose": false, "of_dteq": -4.059999999999945, "py_dteq": 16.35261500909337, "dz_signs": true, "dz_mag_1x": false, "high_T0_no_regress": false, "cvode_Teq_vs_e152": 0.0, "cvode_unchanged": true}`

## timeout_700_60_1 (T=700, p=60, φ=1.0)

| toggle | τ_main [ms] | Teq | ΔTeq vs CVODE | ΔZ_C | ΔZ_H | ΔZ_O | wall [s] | fail |
|--------|------------:|----:|-------------:|-----:|-----:|-----:|---------:|------|
| Tfreeze_on | 3.67 | 3e+03 | -5e+01 | -0.00255 | -0.000668 | 0.00222 | 2e+01 | ok |
| Tfreeze_off | 3.7 | N/A | N/A | N/A | N/A | N/A | 2e+03 | wall_timeout |
| cvode_ref | 3.6 | 3e+03 | 0 | 4.41e-06 | 6.95e-07 | 6.45e-06 | 8e+01 | ok |

Py-QSS: τ_main=3.71 ms, ΔTeq=-3e+01 K, ΔZ_C=-0.00352, ΔZ_H=-5.02e-05, ΔZ_O=0.00796, wall=1.8 s

**Gate (timeout_700_60_1):** PASS — `{"complete_ok": true, "wall_vs_cvode_2x": true}`

## timeout_900_60_1 (T=900, p=60, φ=1.0)

| toggle | τ_main [ms] | Teq | ΔTeq vs CVODE | ΔZ_C | ΔZ_H | ΔZ_O | wall [s] | fail |
|--------|------------:|----:|-------------:|-----:|-----:|-----:|---------:|------|
| Tfreeze_on | 0.367 | 3e+03 | -4e+01 | 0.00154 | -0.000753 | -0.00695 | 3 | ok |
| Tfreeze_off | 0.406 | N/A | N/A | N/A | N/A | N/A | 2e+03 | wall_timeout |
| cvode_ref | 0.265 | 3e+03 | 0 | 4.43e-06 | 6.65e-07 | 6.93e-06 | 1e+01 | ok |

Py-QSS: τ_main=0.361 ms, ΔTeq=-2e+01 K, ΔZ_C=-0.000206, ΔZ_H=0.00104, ΔZ_O=0.0113, wall=0.35 s

**Gate (timeout_900_60_1):** PASS — `{"complete_ok": true, "wall_vs_cvode_2x": true}`


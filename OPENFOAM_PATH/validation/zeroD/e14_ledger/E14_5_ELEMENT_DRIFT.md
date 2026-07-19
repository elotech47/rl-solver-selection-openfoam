# E14.5 — Element-drift audit (gate revised, not bug found)

## Thesis

Teq ≤ 2 K assumed **element-conserving** integration. α-QSS/CHEMEQ2 does not
conserve atoms exactly; small per-window drift → different equilibrium mountain.
Python-QSS shows the same hot-Teq signature (+10.7 K). E14 ledger: **no bookkeeping bug**.

## Results

| Framework | Solver | Teq [K] | max\|ΔZ\| | T_HP@drifted | T_HP@orig elems | Closing | Mechanism |
|-----------|--------|--------:|----------:|-------------:|----------------:|---------|-----------|
| OF | CVODE | 2608.75 | 7.277e-04 | 2609.43 | 2602.86 | True | control |
| OF | QSS | 2647.95 | 6.370e-03 | 2648.58 | 2611.47 | True | **element_drift** |
| Py | CVODE | 2601.02 | 8.915e-11 | — | — | — | control |
| Py | QSS | 2611.70 | 3.224e-03 | 2612.70 | 2620.05 | True | **element_drift** |

- ΔTeq(Py) = **+10.67 K**; ΔTeq(OF) = **+39.20 K** (ratio **3.7×**)

OF-QSS: T_obs ≈ T_HP@drifted; T_HP@original elems differs → **different mountain**.

## Verdict

**Component B closes** as documented CHEMEQ2 element-drift property.
OF/Py ΔTeq amplitude ratio → **Component A** (E15 signature map).

```json
{
  "E14_bookkeeping": "ruled_out",
  "OF_note": "Z on sumY-normalized Y; closing uses h=h(T,Y) Cantera-consistent",
  "OF_QSS_maxAbs_dZ": 0.006369953043069754,
  "OF_CVODE_maxAbs_dZ": 0.00072766355994347,
  "OF_QSS_closing_PASS": true,
  "OF_QSS_T_obs": 2647.95,
  "OF_QSS_T_HP_drifted": 2648.5812155329404,
  "OF_QSS_T_HP_original_elems": 2611.4691354618108,
  "OF_delta_Teq": 39.19999999999982,
  "OF_QSS_mechanism": "element_drift",
  "Py_delta_Teq": 10.674199712181235,
  "Py_QSS_maxAbs_dZ": 0.003223717200006075,
  "Py_closing_PASS": true,
  "Py_mechanism": "element_drift",
  "ratio_OF_over_Py_deltaTeq": 3.6724064620287526,
  "Component_B": "closed_as_CHEMEQ2_element_drift",
  "Component_A_next": "OF/Py \u0394Teq amplitude ratio is per-window slack (E15 map)"
}
```

Advisor packet: this file + `E14_REPORT.md` + `E14_5_ELEMENT_DRIFT.json`.

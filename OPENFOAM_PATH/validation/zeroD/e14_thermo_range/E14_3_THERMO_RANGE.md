# E14.3 — QSS-path ha/cp thermo-range audit

## ESI `janafThermo::coeffs(T)` (behaviour used by QSS)

If T < Tcommon use lowCpCoeffs; else use highCpCoeffs. No blending across Tcommon. Per-species Tcommon from thermo file. QssCellOde calls specieThermo[i].ha(p,T) / .cp(p,T) each odefun evaluation — no cross-window coeff cache.

Production foam has harmonized Tcommon (typically 1000 K).

## Numerical check (5 pins × 10 species)

| Metric | Value | Gate |
|--------|-------|------|
| max rel \|cp\| | 7.7658e-07% | <0.1% |
| max rel \|ha\| | 2.3258e-05% | <0.1% |
| PASS_cp | True | |
| PASS_ha | True | |

Worst: `{'species': 'nc12h26', 'foam_name': 'nc12h26', 'T': 900.0, 'Tcommon': 1000.0, 'branch': 'low', 'cp_foam': 609127.7358716734, 'cp_cantera': 609127.7311412891, 'rel_cp': 7.76583315675595e-09, 'ha_foam': -9669500.696249148, 'ha_cantera': -9669502.9451387, 'rel_ha': 2.3257550726120184e-07}`

If PASS → focus stays on RR/ledger (E14.2/4). Mismatch → in-scope E14 thermo fix.

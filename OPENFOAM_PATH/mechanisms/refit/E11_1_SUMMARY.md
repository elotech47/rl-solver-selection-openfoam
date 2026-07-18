# E11.1 thermo refit trade study

Source: `/Users/el0tech/Documents/research_code/solver_selection/OPENFOAM_PATH/mechanisms/n-dodecane.yaml`
Target window: **[300, Tc, 3500]** K
Selected: **Tc_1000** (Tc=1000 K)

## Trade

| Tc | worst species | max\|Δcp\|/cp | max\|Δhs\| [kJ/kg] | fails |
|---:|---------------|---------------:|-------------------:|------:|
| 1000 | c8h17coch2 | 0.4295% | 3.6589 | 4/106 ← selected |
| 1400 | ch4 | 0.6857% | 3.4394 | 13/106 |

## Notes

- `ch3o` original Thigh=3000 K: high-range NASA poly **extrapolated** to 3500 K as cp targets above 3000 K; gate still applied on [300,3000].
- `h` single-range (cp=5/2·R): both low/high identical; unit-tested to machine precision.
- Gates: max\|Δcp\|/cp≤0.2%, max\|Δhs\|≤2.0 kJ/kg, cp continuity≤0.1 J/(kg·K), cp>0.

## Gate failures

- c8h17coch2: rel_cp=0.4295% hs=3.6589 kJ/kg cont=2.274e-12 cp_min=1675.2 gates(cp/hs/cont/pos)=False/False/True/True
- c3h4-a: rel_cp=0.3051% hs=2.5941 kJ/kg cont=4.547e-13 cp_min=1487.0 gates(cp/hs/cont/pos)=False/False/True/True
- oh: rel_cp=0.2619% hs=0.8028 kJ/kg cont=1.592e-12 cp_min=1709.5 gates(cp/hs/cont/pos)=False/True/True/True
- c2h6: rel_cp=0.1934% hs=2.1548 kJ/kg cont=0.000e+00 cp_min=1726.0 gates(cp/hs/cont/pos)=True/False/True/True

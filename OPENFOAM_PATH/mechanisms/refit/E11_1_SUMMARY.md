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
# E11.1 add-ons — equilibrium invariance & effect-size

## (1) Equilibrium invariance (HP, Z∈[0.02,0.12] × p∈{10,30,60} atm)

- max\|ΔT_equil\| = **0.0079 K** (gate ≤1 K: **PASS**)
- max\|ΔY_major\| = **2.905e-07** (gate ≤1e-5: **PASS**)

| Z | p [atm] | T_orig [K] | T_refit [K] | ΔT [K] | max\|ΔY\| |
|--:|--------:|-----------:|------------:|-------:|---------:|
| 0.020 | 10 | 1531.20 | 1531.20 | -0.0017 | 3.55e-09 |
| 0.020 | 30 | 1531.25 | 1531.25 | -0.0017 | 2.70e-09 |
| 0.020 | 60 | 1531.27 | 1531.27 | -0.0017 | 2.27e-09 |
| 0.040 | 10 | 2151.61 | 2151.61 | -0.0031 | 1.20e-07 |
| 0.040 | 30 | 2155.15 | 2155.14 | -0.0031 | 9.18e-08 |
| 0.040 | 60 | 2156.78 | 2156.77 | -0.0031 | 7.75e-08 |
| 0.060 | 10 | 2580.65 | 2580.64 | -0.0041 | 2.91e-07 |
| 0.060 | 30 | 2617.06 | 2617.06 | -0.0044 | 2.44e-07 |
| 0.060 | 60 | 2636.81 | 2636.80 | -0.0045 | 2.11e-07 |
| 0.080 | 10 | 2521.19 | 2521.19 | -0.0056 | 3.19e-08 |
| 0.080 | 30 | 2530.54 | 2530.54 | -0.0056 | 3.46e-08 |
| 0.080 | 60 | 2534.35 | 2534.34 | -0.0056 | 3.83e-08 |
| 0.100 | 10 | 2263.65 | 2263.65 | -0.0066 | 1.12e-07 |
| 0.100 | 30 | 2265.88 | 2265.87 | -0.0067 | 1.16e-07 |
| 0.100 | 60 | 2266.79 | 2266.78 | -0.0067 | 1.18e-07 |
| 0.120 | 10 | 2015.58 | 2015.57 | -0.0079 | 1.63e-07 |
| 0.120 | 30 | 2016.15 | 2016.14 | -0.0079 | 1.64e-07 |
| 0.120 | 60 | 2016.39 | 2016.38 | -0.0079 | 1.64e-07 |

## (2) Effect-size — 4 strict-gate misses

Peak Yi along MidT (800 K, 10 atm) × species property error → nominal mixture-relative contribution (cp_mix≈1400 J/kg/K).
Expected ≤ **1e-04**. Overall: **PASS**

| species | peak Y | T@peak | max\|Δcp\|/cp | max\|Δhs\| [kJ/kg] | max mix-rel cp | max mix-rel hs | ≤1e-4 |
|---------|-------:|-------:|---------------:|-------------------:|---------------:|---------------:|:-----:|
| c8h17coch2 | 3.933e-07 | 885 | 0.430% | 3.659 | 1.53e-09 | 4.88e-11 | Y |
| c3h4-a | 1.279e-04 | 1654 | 0.305% | 2.594 | 8.55e-07 | 4.23e-08 | Y |
| oh | 6.638e-03 | 2273 | 0.262% | 0.803 | 1.09e-05 | 1.40e-06 | Y |
| c2h6 | 7.671e-04 | 1394 | 0.193% | 2.155 | 3.58e-06 | 4.03e-07 | Y |

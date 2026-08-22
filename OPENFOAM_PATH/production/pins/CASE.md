# Case pin — opposedJet_E18

| Item | Value |
|------|-------|
| Case | `cases/opposedJet_E18` |
| Geometry | L = 0.008 m, V = ±0.4 m/s (a = 100 s⁻¹) |
| p / T_air / T_fuel | 10 atm / 1000 K / 300 K |
| Mesh | 200×100 (20 000 cells), mid refined |
| Freeze | **t = 0.05 s** (chemistry off Stage 1) |
| Chem window | freeze + **0.009 s** → **endTime = 0.059** |
| Write | Pack **20 fields** every `1e-04` s (binary+gzip): `T U p solverFlag policyFlag chemCpuTime oh o o2 h h2 h2o h2o2 ho2 co co2 ch2o c2h4 nc12h26 n2`. No full-`Yi` dumps. |

Do not change geometry without a new Stage 0/1 and a new pin date.

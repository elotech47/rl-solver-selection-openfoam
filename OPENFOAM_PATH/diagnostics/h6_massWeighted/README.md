# H6 diagnostic instruments (retired under Option R)

These headers bypassed `cellMixture` THE by Newton-inverting `Σ Yi·Hs_i`
during the original heterogeneous-Tcommon campaign (E8–E10).

**Production path (Option R, 2026-07-17):** harmonized-Tcommon refit thermo
`mechanisms/refit/` + stock `thermo.correct()` / `THE`. Do not include these
in shipping solvers unless diagnosing the *original* heterogeneous foam thermo
(`mechanisms/foam_original_heterogeneous/` or `cases/*/constant_original_hetero/`).

- `massWeightedT.H` — chemFoam `hEqn.H`
- `massWeightedCorrect.H` — reactingFoam `EEqn.H`

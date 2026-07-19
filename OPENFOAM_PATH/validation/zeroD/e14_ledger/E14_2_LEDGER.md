# E14.2 — MidT ledger results (Campaign 4)

## Runs

`OFRL_DEBUG_INVARIANTS=1`, Option R MidT_MidP, `validation/zeroD/e14_midt/{cvode,qss}/`.

| Solver | Tend [K] | wall [s] | CSV rows |
|--------|----------|----------|----------|
| CVODE  | 2608.75  | 20       | 3522     |
| QSS    | 2649.06  | 5        | 3523     |

**Teq(QSS) − Teq(CVODE) = +40.3 K** (gate ≤ 2 K) — still FAIL.

## Decision table

| # | Test | QSS | CVODE | Action |
|---|------|-----|-------|--------|
| 1 | ΔY_applied vs ΔY_RR | PASS (max\|diff\| ≤ 1.1e-16) | PASS | — |
| 2 | dIntegratedHeat vs −Σ Hc·ΔY_RR | PASS (0) | PASS | — |
| 3 | −Σ Hc·ΔY_app vs RR | PASS (~1e-9) | PASS | — |
| 4 | Teq ≤ 2 K | FAIL (+40.3 K) | control | escalate / E14.3 |

`fix_scope` from `e14_ledger.py`: **escalate_or_E14.3_thermo_range**.

## Notes

- `nSub == 1` every window (no chemistry subcycling at Δt=1e-6).
- `|T_int − T_cell|` peaks ~33 K during runaway (ODE T discarded by ESI; cell T from h→Newton) — expected, not a ledger bug.
- End-state: CVODE `T_int == T_cell`; QSS within ~1 K of Newton probe.
- JSON: `validation/zeroD/e14_ledger/e14_2_ledger.json`.

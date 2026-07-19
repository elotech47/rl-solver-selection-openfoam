# E14 — Energy ledger campaign (Campaign 4)

## Verdict

**ESCALATE** — no localized RR/Δt/ρ/Hc bookkeeping bug found.

Ledger invariants are green on MidT Option R for both QSS and CVODE, yet

**Teq(QSS) − Teq(CVODE) = +40.3 K** (gate ≤ 2 K).

Per plan stop condition: *everything consistent and Teq still ~+39 K → escalate
with full ledger (no theorizing)*. **No unilateral QSS algorithm fix applied.**

## E14.1 Instrumentation

- Env `OFRL_DEBUG_INVARIANTS=1` → `e14_invariants.csv`
- Shared stash `libofRlInvariants` (qss/cvode `recordSolve`; chemFoam ledger)
- Bit-identical when unset (env gate only)

## E14.2 MidT ledger

See `e14_ledger/E14_2_LEDGER.md` and `e14_ledger/e14_2_ledger.json`.

| Check | Result |
|-------|--------|
| ΔY_applied vs ΔY_RR | PASS (~1e-16) |
| dIH vs −Σ Hc·ΔY_RR | PASS (0) |
| Teq ≤ 2 K | **FAIL (+40.3 K)** |

## E14.3 Thermo-range

QSS-path NASA `ha`/`cp` vs Cantera-refit at 5 pins × 10 species:

- max rel cp ≈ **7.8e-9**
- max rel ha ≈ **2.3e-7**

**PASS** — no thermo-range / coeff-selection defect. Details:
`e14_thermo_range/E14_3_THERMO_RANGE.md`.

## E14.4 Re-acceptance

| Gate | Result |
|------|--------|
| Teq ≤ 2 K | FAIL (+40.3 K) |
| Ledger / ΔY | green |
| ΣY | (unchanged Option R path) |
| CVODE MidT control | Tend=2608.75 K (matches prior E13) |

**Component B (−19% / +4.2% / +39 K) not explained by accounting or NASA range.**

Escalation packet for advisor: full CSV under `e14_midt/{qss,cvode}/e14_invariants.csv`.

## Implication for E15

E15 toggles **blocked** until advisor disposition of this escalation (plan: E15
only after E14.4 green). E15.1 config-diff table may still be drafted offline.

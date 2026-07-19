# E15.1 — OF-QSS vs CanteraQSSODE config diff

Drafted under Campaign 4 after E14 **escalation** (ledger green, Teq still +40 K).
**E15.2 toggles / E15.3 ADOPT gate are BLOCKED** until advisor disposition of E14.

## Config table

| Knob | Handoff `CanteraQSSODE` / `create_qss_solver` | OF `qss` (`qss.C` / coeffs) | Notes |
|------|-----------------------------------------------|-----------------------------|-------|
| State basis | `y = [T, Y…]` mass fractions | `y = [T, c…]` concentrations | Outer chemFoam still applies RR→Y |
| Energy in odefun | `h_form` = standard enthalpies; T-freeze on corrector | mole `ha(p,T)` / `cp(p,T)` each call; T not frozen | E13.3 |
| `epsmin` | default **0.01** (`create_qss_solver`); strategy often **0.02** | **0.02** (`qssCoeffs`) | mismatch vs utils default |
| `epsmax` | default **20** | **100** | OF more permissive |
| `dtmin` | 1e-15 | 1e-12 | |
| `dtmax` | 1e-6 | 1e-6 (capped by window) | |
| `abstol` | 1e-8 | 1e-11 | OF tighter |
| `itermax` | 2 | 2 | match |
| T-freeze on corrector | **yes** (cache T/ρ/cp/hform) | **no** (re-eval thermo every call) | major conformance candidate |
| Substep controller | integrator internal + outer `num_steps` | `suggestDeltaT` \|dT\|≲25 K + StdChem subcycle | |
| `ymin` / floors | species floor in integr; T≥300 in ODE | species `max(c,0)`; T clamp [250,4500] | |
| Restart / landing | policy / window restart in blackbox | chemFoam fixed Δt=1e-6 MidT | |

## Provisional E15.3 preference (from plan)

**ADOPT ACCURATE** — conditional on post-E14 cost/accuracy contrast vs CVODE.
**Not finalized:** E14.4 did not go green.

## Next (when unblocked)

1. E15.2 — toggle each row at T1301/T1701/T2001 + cool-flame; cost-per-window grid
2. E15.3 — HUMAN gate with both signatures + costs
3. E15.4 — chosen config re-acceptance → unblock 2D QSS

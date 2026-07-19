# E16.3 — In-OF rlAdaptive gate

**Date:** 2026-07-19  
**Amended:** 2026-07-19 (human) — wiring vs usage gates separated.

**Config:** `chemistryType { solver ode; method rl; }`, TorchScript `policy.ts`,
QSS T-freeze ON / `epsmin=0.02`, `numSteps=20`, `maxChemDeltaT=1e-6`.  
**Window (this report):** `t_end = 1 ms` — **pre-ignition only** for MidT/NTC;
usage comparison on this window is **not** a binding gate (see amendment).

## Wiring status

| Item | Status |
|------|--------|
| Foam `policy_manifest` + `loadPolicyManifest` | **DONE** |
| LibTorch + C ABI bridge | **DONE** |
| `integrateQss` / `integrateCvode` | **DONE** |
| Ykey/history → policy → per-cell dispatch | **DONE** |
| RTS `ode` + `method rl` | **DONE** |
| Policy loads (no silent all-CVODE) | **DONE** |
| Decision log | **DONE** (E16.3b adds `p` column) |

## Amendment (binding)

| Gate | Verdict |
|------|---------|
| **WIRING** | **PASS** |
| **Usage ±5 (1 ms window)** | **INCONCLUSIVE** — design + window artifacts suspected (closed-loop fork before ignition; single-flip sensitivity). **Retired** as a scalar gate — see `DECISIONS.md` / E16.3b. |

## Cases (1 ms scout)

| Case | T0 [K] | p [atm] | φ | Notes |
|------|-------:|--------:|--:|-------|
| MidT | 800 | 10 | 1.0 | Pre-ignition; T_final ~962 K |
| NTC  | 700 | 10 | 1.0 | No runaway in 1 ms |

## Scout metrics (non-binding)

- MidT CVODE%: OF=2.0 Py=25.5 (Δ=23.5) — expected under early fork
- NTC CVODE%: OF=14.0 Py=19.6 (Δ=5.6)
- Final T vs cvodeOnly: MidT |ΔT|=6.3 K **OK**; NTC ΔT=0
- Pairwise time-index agreement MidT 76% / NTC 86% — **not** the parity metric

## Next

**E16.3b required** before E17 rlAdaptive smoke:
teacher-forced ≥99%, extended windows past ignition, progress-space (T) plots.
See `validation/e16_parity/E16_3B_GATE.md`.

Artifacts: `validation/e16_parity/e16_3_runs/`.

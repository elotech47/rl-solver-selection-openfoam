# E12 opposed-jet — status

**Date:** 2026-07-18  
**Config:** Option R refit thermo, stock THE, CVODE-only, air 1100 K, **p = 10 atm** (MidP analogue for tractable τ_ign).

## Mesh / numerics

| Item | Value |
|------|------:|
| Cells | **3200** (80×40) — 10k-cell smoke first verified propSanity; full 10–20k deferred (≈40 s/CVODE-step) |
| Solver | `reactingFoamDebug` + `cvode` |
| endTime | 0.005 s |
| maxDeltaT | 1e-5 s |

## E12.2 property sanity (from 10k-cell smoke + ongoing run)

| Metric | Result |
|--------|--------|
| max\|cpBlend−ΣYi·cp\|/cp | **2.06e-16** (round-off) |
| Newton / JANAF FATAL | none so far |
| T BC range | 300–1100 until ignition |

Artifacts: `validation/zeroD/e12_opposedJet_smoke/` (partial), `e12_opposedJet/` (ignition run in progress), case `e12_prop_sanity.csv`.

## Acceptance (pending ignition run completion)

- [ ] max(T) ≫ 1100 K (runaway)
- [ ] stabilized flame / no unphysical T
- [ ] ΣY / species bounds
- [ ] propSanity blend remains ~round-off through front

Wall estimate: ~11 s/step × 500 steps ≈ **1.5 h**.

# E16.1 — Interface freeze audit

**Date:** 2026-07-19  
**Tag context:** `validation-baseline-v1` (`823b1c2`)  
**Purpose:** Single source of truth for zero-shot policy deployment (Campaign 5 / master §4.2).

## Artifacts (SHA-256)

| File | Bytes | SHA-256 |
|------|------:|---------|
| `handoff/checkpoints/best_offline_eval2.pt` | 572061 | `5d57f7e00fe940906c9da0a1ea7fda47a9936496412531882cd72227ae98184c` |
| `solver_selection_0D/checkpoints/best_offline_eval2.pt` | 572061 | *(identical to handoff copy)* |
| `OPENFOAM_PATH/policy/policy.ts` | 199512 | `d3975b167d493befa553467b68a03749e906fb1f348322ccd77a97935834267f` |
| `OPENFOAM_PATH/policy/policy_manifest.json` | 1987 | `28784231c0c2f3f8b2c2a44d7e9beda2c60b7524e7650fcafad3e99a2fe846ca` |

`OPENFOAM_PATH/policy/best_offline_eval2.pt` is **gitignored** (`*.pt`) but must
exist locally for tests; SHA-256 above is the pin. Copy from
`handoff/checkpoints/best_offline_eval2.pt` (identical hash) if missing.

## Feature contract (19-D)

Source of truth: `policy_manifest.json` (also embedded in C++ `buildObservation19` / `normalizeObs`).

| # | Name | Transform |
|---|------|-----------|
| 0 | `T_norm` | `(T−300)/2000` |
| 1–8 | `log10_Y_*` | `log10(max(|Y|, 1e-20))` for OH,H2O,O2,H2,H2O2,O,H,N2 |
| 9 | `P_norm` | `log10(P / 101325)` |
| 10 | `dlog10_T` | `log10(T) − log10(T_prev)` — **Δlog10, not /Δt** |
| 11–18 | `dlog10_Y_*` | same for key species |

Then obs_rms: `(x − mean) / (√var + 1e-8)`, clip to ±10 (`obs_clip`).

## Decision rule (must match Ember paper pipeline)

1. Forward pass → logits (2-class).
2. Softmax → probabilities; confidence = max(p).
3. Action = **argmax**.
4. If confidence **< 0.6** → force **CVODE** (action 0).

Recorded in manifest `decision_rule` / `confidence_threshold` / `action_map`.
Python: `RLSolverSelector` / `AdaptiveRLStrategy`. C++: `PolicyRuntime::inferBatch`.

## Cold-start (t = 0 / first decision)

| Stack | Behavior |
|-------|----------|
| Python `RLSolverSelector` | `prev_state is None` → set prev = current, then Δlog10 = **0** |
| Python `ObservationBuilder.reset(IC)` then `build(IC)` | prev = IC → Δlog10 = **0** |
| Python batch (Ember) | first call / grid change → temporal features **explicitly zero** |
| C++ `buildObservation19(..., hasPrev=false)` | temporal slots left **0** |
| C++ `rlChemistryModel` | `hasPrev = (Tprev_ > SMALL)`; initially false → matches |

**Contract:** first policy query has zero temporal features. Do not invent cold-start guards that change this without discussion.

## Wiring gaps (block E16.2 / E16.3 / E17 rlAdaptive)

Documented in `src/rlChemistryModel/rlChemistryModel.C`:

1. Key-species mass fractions **not extracted** (`Ykey[8] = {}`).
2. `obs_rms` mean/var **not loaded** from manifest into `PolicyManifest` (empty → near-identity normalize).
3. Per-cell QSS/CVODE dispatch **not wired** — falls through to `StandardChemistryModel::solve`.

E16.2 must compare Python features+decisions to C++ `buildObservation19` + TorchScript (or a faithful Python reimplementation of the C++ contract fed by TorchScript), **not** only the existing `tests/test_decision_parity.py` Python↔Python clone (which already reports 600/600 — insufficient for the zero-shot claim).

## Acceptance for E16.1

- [x] Hashes recorded
- [x] Feature order + Δt semantics documented
- [x] Decision rule documented
- [x] Cold-start documented
- [x] Gaps that block E16.2/.3 listed (no silent pass)

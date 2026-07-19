# Campaign 5 — Baseline freeze → E16 policy parity → E17–E18 2D RL

**Instruction document for the coding agent.** Continuation of DEBUG_REPORT.md
(E15.2b CONFORM GATES GREEN). Configuration of record: Option R + stock THE +
conform QSS (T-freeze, epsmin=0.02) + CVODE. No stack changes without human gate.

Full instruction: see conversation / keep this STATUS as the live tracker.
Canonical freeze tag: **`validation-baseline-v1`** (alias `e15-conform-baseline-v1`).

## Phase 0 housekeeping

| Item | Status |
|------|--------|
| 1. Tag `validation-baseline-v1` alias | **DONE** → `823b1c2` |
| 2. MANIFEST + Lexar sync | **DONE** — `MANIFEST.md`, `/Volumes/Lexar/.../ac647e1/` |
| 3. Frozen rung (b)/(c) table | **DONE** — `FROZEN_RUNG_BC_ACCEPTANCE.md` |
| 4. THESIS_NOTES 800/10/1.5 residual line | **DONE** (this commit wave) |

## Live trackers

| Track | Status | Notes |
|-------|--------|-------|
| E16.1 interface freeze | **DONE** | `validation/e16_parity/E16_1_INTERFACE_FREEZE.md` + DECISIONS |
| E16.2 replay ≥99.9% | **PASS (contract+TS)** | 800/800 decisions; max feature abs 9.5e-7. Native OF LibTorch path still needs Ykey/obs_rms wiring |
| E16.3 0D rlAdaptive | **BLOCKED** — `rlChemistryModel` still scaffolds (Ykey={}, parent solve only) |
| E17.1 cvodeOnly smoke | **NEEDS IGNITING BC** — E12.1-redo @1250 K did **not** ignite |
| E17 qss/rl smoke | waits E16.3 wiring + igniting case |
| E17b LONI Apptainer | **SCAFFOLD** — `container/LONI.md` + `loni-of-rl.def` (build needs LONI login) |
| E18 production | waits E16+E17+E17b green; **LONI only** |

## Known blockers (do not paper over)

1. **`rlChemistryModel::solve`**: Ykey extraction stubbed to zeros; no per-cell QSS/CVODE dispatch; `obs_rms` not loaded from manifest → near-identity normalize.
2. **E17 ignition**: need Cantera-sized opposed-jet BC that actually runs away (E12.1-redo failed).
3. **E16.2 true gate**: must compare Python pipeline vs C++ `buildObservation19` + TorchScript `policy.ts`, not Python vs Python contract clone.

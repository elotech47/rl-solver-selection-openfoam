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

| Track                  | Status                                                                           | Notes                                                                                                  |
| ------------------------| ----------------------------------------------------------------------------------| --------------------------------------------------------------------------------------------------------|
| E16.1 interface freeze | **DONE**                                                                         | `validation/e16_parity/E16_1_INTERFACE_FREEZE.md` + DECISIONS                                          |
| E16.2 replay ≥99.9%    | **PASS (contract+TS)**                                                           | 800/800 decisions; max feature abs 9.5e-7                                                              |
| E16.3 0D rlAdaptive | **WIRING PASS / usage INCONCLUSIVE** | ±5 retired; see `E16_3_GATE.md` |
| E16.3b teacher-forced + extended free-run | **APPROVED** | TF **100%**. Free-run usage band **waived** (fork analysis). Binding gate = final-state vs cvodeOnly. Standing: accuracy hard gate + log \|p−0.5\|<0.1 OOD. `E16_3B_GATE.md` |
| E16.4 0D paper-conditions suite | **GREEN — E16 CLOSED** | Recalibrated gates; chemCpuTime fix; reverse TF 100% C1/C2. `E16_4_GATE.md` |
| E16.5 decision/feature clock | **GREEN** | τ_dec = num_steps×dt_ref physical-time clock; snapshot Δlog; irregular MidT + fixed bit-identical + TF 40/40. Blocks E17 rlAdaptive until green — now open. `E16_5_GATE.md` |
| E17.1 cvodeOnly smoke | **IN PROGRESS (remote kit)** | Mac scout slow; use `validation/zeroD/e17_remote/README.md` on multi-core linux/amd64 |
| E17 qss/rl smoke | waits E17.1 igniting BC; **rlAdaptive unblocked by E16.5** |
| E17b LONI Apptainer | **DEFERRED** — waiting on allocation access; scaffold kept (`container/LONI.md`) |
| E18 production | waits E16+E17+E17b; **LONI only when access lands** |

## Known blockers (do not paper over)

1. **E17 ignition:** need Cantera-sized opposed-jet BC that actually runs away (E12.1-redo failed).
2. **LibTorch in OF process (arm64):** requires `LD_PRELOAD` + MKLDNN off (`e16_4_run_one.sh`).

## Standing conditions (post–E16.3b / E16.4)

1. Accuracy vs **cvodeOnly** = hard gate on subsequent runs.
2. Log **OOD** = fraction of decisions with \|p−0.5\| < 0.1.
3. **E16 CLOSED GREEN** (2026-07-19) — proceed to E17 rlAdaptive smoke when igniting BC exists.

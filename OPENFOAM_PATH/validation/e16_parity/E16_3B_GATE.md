# E16.3b — Teacher-forced parity + extended free-run

**Date:** 2026-07-19  
**Gate redesign:** see `DECISIONS.md` (E16.3b).

- **Parity** = teacher-forced in-process ≥99% decision agreement  
- **Free-run** = phase-consistency in T-space + usage within 0.5–2× per phase  
  + final-state vs cvodeOnly (≤ paper 0D envelope, |ΔT|≲50 K)  
- **Retired:** ±5-point scalar CVODE-usage gate (single-flip fork sensitivity)

## Teacher-forced (true in-loop parity)

Drive C++ `buildObservation19` + `normalizeObs` + TorchScript with **live**
`Tprev`/`YkeyPrev` history on the recorded Python AdaptiveRL state tape.

| Case | n | agree | % |
|------|--:|------:|--:|
| MidT | 170 | 170 | **100.0** |
| NTC  | 401 | 401 | **100.0** |
| **All** | **571** | **571** | **100.0** |

**PASS** (≥99%). Mismatches: none (no |p−0.5| table needed).

Artifact: `e16_3b_runs/teacher_forced_summary.json`,
`{MidT,NTC}_teacher_forced.csv`.

## Extended free-run (progress-space)

Windows: MidT `t_end=3.4 ms`, NTC `t_end=8.0 ms` (≈1.4× Cantera τ_ign).

### MidT

| Metric                   | OF rlAdaptive         | Python AdaptiveRL          |                        |
| --------------------------| ----------------------:| ---------------------------:| ------------------------|
| CVODE% (all)             | 0.59                  | 7.65                       |                        |
| CVODE% pre (T&lt;1730 K) | 0.83                  | 11.93 → **outside 0.5–2×** |                        |
| CVODE% post              | 0.0                   | 0.0 → OK                   |                        |
| Final T vs OF cvodeOnly  | 2605.6 vs 2620.7 K, \ | ΔT\                        | =**15.1 K** → **PASS** |
| Wall [s]                 | 40 (rl) / 56 (cvode)  | —                          |                        |

Progress plot: `e16_3b_runs/MidT_decisions_vs_T.png`

**Fork note (human review):** OF takes CVODE only at the cold-start query
(T=800 K, p=P(QSS)≈0.175, conf≈0.825→CVODE). Python continues to select CVODE
through early heat-up (T≈800.0–802 K, several queries with p near 0.5). After
that both stay QSS in post-ignition. Teacher-forced 100% on the Py tape shows
this is **closed-loop trajectory fork**, not a feature-builder bug.

### NTC

| Metric | OF rlAdaptive | Python AdaptiveRL |
|--------|--------------:|------------------:|
| CVODE% (all) | 1.75 | 5.74 |
| CVODE% pre (T&lt;1654 K) | 2.46 | 8.81 → **outside 0.5–2×** |
| CVODE% post | 0.0 | 0.0 → OK |
| Final T vs OF cvodeOnly | 2528.5 vs 2559.8 K, \|ΔT\|=**31.3 K** → **PASS** |

Progress plot: `e16_3b_runs/NTC_decisions_vs_T.png`

**Fork note:** OF uses 7 early CVODE decisions at T≈700 K (p spanning ~0.18–0.57);
Python uses 23 early CVODE queries in the same T band. Post-ignition both QSS.

## Probability logging

Every decision now records `p = P(QSS)` (OF `rl_decisions.csv`; Py `decisions.csv`
+ `state_tape.csv`).

## Outcome routing

| Check | Result |
|-------|--------|
| Teacher-forced ≥99% | **PASS (100%)** |
| Free-run usage 0.5–2× per phase | **FAIL** (pre-ignition OF under-uses CVODE vs Py) |
| Final-state \|ΔT\|≲50 K vs cvodeOnly | **PASS** (both cases) |

**Routing:** Teacher-forced green but free-run usage still diverges beyond band  
→ **human review** before E17 rlAdaptive smoke (fork features/probabilities above).  
Do **not** treat as a builder bug (TF proves the in-process path).

## Verdict

**APPROVED (human review, 2026-07-19)** — Teacher-forced parity **CLOSED GREEN**
(100%). Free-run usage band **waived** per fork analysis: TF proves in-process
fidelity; **final-state accuracy vs cvodeOnly** is the binding free-run gate.
Standing conditions for subsequent runs: (1) accuracy vs cvodeOnly remains a
hard gate; (2) log fraction of decisions with \|p−0.5\| < 0.1 as OOD health
metric. Next: **E16.4** paper-conditions suite (blocks E17).

Artifacts: `validation/e16_parity/e16_3b_runs/`.

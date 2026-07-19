# Campaign 5: Baseline freeze → policy parity (E16) → 2D RL campaign (E17–E18)

Instruction document for the coding agent. Continuation of DEBUG_REPORT.md
(E15.2b CONFORM GATES GREEN, advisor-approved). This campaign ends the validation
era and produces the first thesis results: RL solver selection in 2D.

**Configuration of record:** Option R refit thermo + stock THE + conform QSS
(corrector T-freeze, epsmin=0.02) + CVODE (paper-matched settings). No changes
to this stack without a human gate.

**Live tracker:** `validation/CAMPAIGN5_STATUS.md`

## Phase 0 — COMPLETE (2026-07-19)

Commit `823b1c2`, tags `validation-baseline-v1` / alias `e15-conform-baseline-v1`.
Housekeeping (tag alias, MANIFEST+Lexar, rung b/c table, THESIS_NOTES residual)
closed in follow-up commits.

## Sequencing (binding)

```
NOW (parallel):
  ├─ E16.1–.3 (policy parity, Mac)     ── gate for rlAdaptive
  ├─ E17.1 cvodeOnly smoke (Mac)       ── needs igniting opposed-jet BC
  └─ E17b container build on LONI      ── E16.2 replay on x86 waits on E16.1 artifacts

E16 green → E17 qssOnly + rlAdaptive smoke (Mac)
E17 + E17b green → E18 (production, LONI only)
```

## Compute placement

- **Mac:** development, unit tests, 0D, E16, E17 smoke ONLY. Not thesis production.
- **LONI:** ALL E18 + mesh-independence + scaling. Production figures cite HPC only.

## Stop conditions

See Campaign 5 prompt: E16.2 &lt;99.9% systematic; E16.3 CVODE-usage &gt;±5 pts;
E17 overhead &gt;3%; cold-cell pathology; 2D FATAL; E18 Ember centerline fail.

## Definition of done

1. `validation-baseline-v1` + frozen 0D table
2. E16 parity report green
3. E17 three-mode smoke green (Mac)
4. E17b `hpc-baseline-v1` + spot set + SLURM smoke
5. E18 anchor on LONI + analysis scripts
6. THESIS_NOTES through E18 anchor

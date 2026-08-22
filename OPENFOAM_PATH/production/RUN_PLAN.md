# Production run plan — LSU / LONI cluster

Audience: operator submitting thesis twins. Past tense history lives in
`THESIS_NOTES.md` and `validation/zeroD/e18_prep/E18_CAMPAIGN_SUMMARY.md`.

---

## 0. Goal

Produce **matched** chemistry twins on the Ember-matched opposed jet
(`cases/opposedJet_E18`, freeze **t = 0.05 s** → **endTime = 0.059**):

| Arm | Mode | Why |
|-----|------|-----|
| A | `cvodeOnly` | Hard accuracy reference (E16 standing gate) |
| B | `rlAdaptive` | Policy claim (`lambda_1p0_with_base_obs_rms`) |
| C | `qssOnly` | Safety-net baseline (guards only; no policy) |

Same mesh, freeze IC, guards, write interval, and MPI layout across A/B/C.

---

## 1. What **not** to re-run on the cluster

| Skip | Reason |
|------|--------|
| All `e10`–`e16` 0D ladders | Already frozen / tagged `validation-baseline-v1` |
| E17 smoke / forensics | Geometry superseded by E18 |
| E18 Stage 0 scout | Pick already frozen (10 atm / 1000 K / 100 s⁻¹) |
| E18 Stage 1 cold mix | Freeze `0.05/` already in case |
| Mechanism YAML→Foam | Option R already in case `constant/` |
| Policy training | Use exported `policy.ts` + Foam manifest |

Touch those only if a **pin** changes (document in `pins/`).

---

## 2. Priority order (cluster)

### P0 — Bootstrap once per machine/image (≤1 job)

1. Clone repo + copy `opt/libtorch` or run `tools/install_libtorch.sh`.
2. `bash production/scripts/00_bootstrap.sh` → SUNDIALS + wmake stack.
3. Confirm `policy/policy.ts` + `policy/policy_manifest` (snake_case) match pins.
4. Short smoke (optional): `E18_END_TIME=0.0002` `E18_MODES=cvodeOnly` to prove MPI + chemistry.

### P1 — Full twins to **0.059** (three jobs, parallel OK)

| Job | Env | Est. wall (order-of-mag from workstation 8 ranks) |
|-----|-----|-----------------------------------------------------|
| `e18_cvode` | `E18_MODES=cvodeOnly` | Longest — scale NPROC carefully |
| `e18_rl` | `E18_MODES=rlAdaptive` | ~⅔ of CVODE wall at matched *t* (workstation) |
| `e18_qss` | `E18_MODES=qssOnly` | Expect between RL and CVODE; needed for fork |

Submit via `cluster/submit_twins.sh` or individual `.sbatch` files.
**One mode per job** so a CVODE OOM/timeout does not kill RL.

Defaults:

```bash
export FREEZE=0.05          # or auto from case
export E18_END_TIME=0.009   # → endTime 0.059
export E18_WRITE_INTERVAL=1e-04   # pack cadence; 106 Yi are not written
export NPROC=32             # tune to node; keep identical across modes
```

### P2 — Post-process (laptop or login node)

1. `30_extract_results.sh` → `summary.json`, progress CSV, centerline packs.
2. `31_compare_twins.py` → ClockTime, T_max(t), sparse ΔT vs CVODE.
3. ParaView: reconstruct packed fields (`T`, `oh`, `solverFlag`, `chemCpuTime`, …).
4. Freeze numbers into `THESIS_NOTES.md` + update `E18_CAMPAIGN_SUMMARY.md`.

### P3 — Optional ablations (after P1 green)

- τ_dec = Δt (decide every CFD step).
- Higher `NPROC` strong-scaling spot.
- Logger fix rebuild (policy vs effective `solverFlag`) then re-extract usage maps only if chemistry bit-identical.

---

## 3. Success criteria (thesis gates)

| Gate | Criterion |
|------|-----------|
| Completion | All three modes reach `endTime=0.059`, exit 0, no SIGFPE |
| Accuracy | RL (and QSS) vs cvodeOnly: centerline T / OH RMSE within standing band (document); domain T_max class ~2500 K |
| Usage | After logger fix: policy vs effective counts agree with `solverFlag` |
| Cost | Report wall ClockTime and MPI-sum chem CPU; do **not** claim QSS% from broken `rlUsage` alone |
| Repro | `pins/` + `runs/<id>/MANIFEST.txt` list image, commit, NPROC, policy hash |

---

## 4. Validation vs production map

```text
validation/zeroD/e18_prep/     → R&D scripts (source of truth for Stage-2 logic)
production/scripts/            → thin wrappers; OUT → production/runs/
production/runs/<timestamp>/   → thesis dumps (gitignored)
```

Workstation E18 dump `stage2_chem_20260720_130353/` is **pilot only**
(cvodeOnly incomplete; RL complete). Cluster P1 supersedes it for claims.

---

## 5. Operator checklist

- [ ] Image: Docker `opencfd/openfoam-default:2312` **or** Apptainer SIF (see `cluster/README.md`)
- [ ] `--entrypoint /bin/bash`; `set +eu` before OF bashrc (`AGENTS.md`)
- [ ] Paths in `chemistryProperties` use container root `/work/...`
- [ ] FOAM_SIGFPE ON unless waived in writing
- [ ] Guards: `TminAccept=250`, `epsY=1e-8`, `epsSumY=1e-2` (E18 production)
- [ ] Policy: `lambda_1p0_with_base_obs_rms` → `policy.ts` + Foam manifest
- [ ] Disk: LONI `/work` inode quota (`showquota`, 4e6 files). Pack **20 fields** every 1e-4 s (`T/U/p` + flags + `oh o o2 h h2 h2o h2o2 ho2 co co2 ch2o c2h4 nc12h26 n2`); **no full Yi**. Delete `case_*/processor*` before resubmit.

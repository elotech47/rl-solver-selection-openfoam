# Agent guide — OpenFOAM RL / QSS solver selection

Living checklist for humans and coding agents working in this repo.
**Update this file whenever a new obvious footgun is found** (same PR/session as the fix).

Canonical short Cursor rule: `.cursor/rules/openfoam-rl-agent.mdc` (always-on pointer here).

---

## 0. How to maintain this guide

1. When a script/run fails for a **setup/infra** reason (paths, Docker, Foam dict syntax, packing), fix the code **and** add a bullet under the right section below with date + one-line “symptom → fix”.
2. Prefer concrete BAD/GOOD snippets over prose.
3. Keep sections scannable; move long narratives to `DECISIONS.md` / `THESIS_NOTES.md` / experiment `*_GATE.md`.

---

## 1. Repository layout (mental model)

| Path | Role |
|------|------|
| `OPENFOAM_PATH/` | All OpenFOAM sources, cases, validation, tools |
| `OPENFOAM_PATH/src/rlChemistryModel/` | RL dispatch + E17.2 guards |
| `OPENFOAM_PATH/src/qssChemistrySolver/` | α-QSS (CHEMEQ2) |
| `OPENFOAM_PATH/cases/chemFoam_0D/` | Single-cell 0D harness |
| `OPENFOAM_PATH/cases/opposedJet_2D/` | E17 2D smoke case |
| `OPENFOAM_PATH/validation/zeroD/e17_remote/` | Multi-core smoke kit (scripts) |
| `OPENFOAM_PATH/validation/zeroD/e17_remote_runs/` | **Runtime dumps** (gitignored except small reports) |
| `OPENFOAM_PATH/validation/zeroD/e17_2/` | E17.2 forensics + minimal repro + gates |
| `OPENFOAM_PATH/production/` | **Thesis / cluster CFD** (`env.qb.sh`, `RUN_PLAN.md`, Slurm) |
| `OPENFOAM_PATH/DECISIONS.md` | Design decisions log |
| `THESIS_NOTES.md` | Committee narrative |

Inside Docker, the mounted tree is **`/work` ≡ `OPENFOAM_PATH`**.

---

## 2. Docker / OpenFOAM environment

### 2.1 Entrypoint

Symptom: `/openfoam/run: source: not found` or empty console and instant exit.

```bash
# BAD — image entrypoint is dash /openfoam/run
docker run --rm -v "$ROOT:/work" opencfd/openfoam-default:2312 bash -lc 'source …'

# GOOD
docker run --rm --platform=linux/amd64 --entrypoint /bin/bash \
  -v "$ROOT:/work" -w /work \
  opencfd/openfoam-default:2312 -lc '…'
```

### 2.2 bashrc + `set -e`

Symptom: container dies with **no output** right after start; empty `console.txt`.

```bash
# GOOD pattern (used by e17 smoke / e17_2 repro)
set +eu
source /usr/lib/openfoam/openfoam2312/etc/bashrc
set -e
set +u
export ROOT=/work
source /work/tools/ofrl_container_env.sh
set +u
```

### 2.3 Shared env

Always `source /work/tools/ofrl_container_env.sh` after bashrc (LibTorch preload, SUNDIALS, `FOAM_USER_*`).

### 2.4 Rebuild after C++ changes

After editing `rlChemistryModel` / integrators / policy runtime:

```bash
wmake -j"$(nproc)" /work/src/rlChemistryModel
# (and sibling libs if you touched them)
```

Smoke kit already wmake’s inside Docker; minimal repro does too. Do not assume host `platforms/` is fresh.

---

## 3. Paths and script ROOT

| Script location | `ROOT` = `OPENFOAM_PATH` via |
|-----------------|------------------------------|
| `validation/zeroD/e17_remote/*.sh` | `$(cd "$(dirname "$0")/../../.." && pwd)` |
| `validation/zeroD/e17_2/*.sh` | **same — three levels** |

Symptom (2026-07-20): `…/validation/validation/zeroD/…` → `ROOT` only went up two levels then re-appended `validation/`.

```bash
# BAD (from e17_2/)
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"   # → …/validation
HERE="$ROOT/validation/zeroD/e17_2"        # doubled

# GOOD
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"  # → …/OPENFOAM_PATH
HERE="$(cd "$(dirname "$0")" && pwd)"
```

Python: from `e17_2/foo.py`, `Path(__file__).resolve().parents[3]` is `OPENFOAM_PATH`.

---

## 4. Foam dictionaries (syntax that actually parses)

### 4.1 Quoted `fileName` paths

Symptom: `Wrong token type - expected string, found punctuation '/'` on `manifest`.

```
// BAD
manifest            /work/policy/policy_manifest;
torchScript         /work/policy/policy.ts;

// GOOD
manifest            "/work/policy/policy_manifest";
torchScript         "/work/policy/policy.ts";
```

### 4.2 Container vs host paths

Policy/manifest paths in `chemistryProperties` written for Docker must be **`/work/...`**. Host `/home/elo/...` paths cause FATAL inside the container. Use `E17_CONTAINER_ROOT=/work` (see `e17_configure_mode.sh`).

### 4.3 chemFoam `initialConditions`

Symptom: `Max of mass fraction sum differs from 1 by ~100` or missing `constantProperty`.

```
// GOOD
constantProperty pressure;
fractionBasis   mass;   // or mole
fractions
{
    n2    0.73;
    o2    …;
    …
}
p    1013250;
T    800;
```

Do **not** put bare `Yi` entries at the top level of `initialConditions`.

Reference: `cases/chemFoam_0D/constant/initialConditions`, `validation/zeroD/e13_qss/of_ic/*/initialConditions`, `e17_2/e17_2_write_ics.py`.

### 4.4 Foam `policy_manifest` keys (not camelCase)

Symptom: `policy_manifest obs_rms size mismatch: mean=0 var=0 obs_dim=19` right after load.

C++ (`policyManifestIO.H`) looks up **snake_case** Foam keys. JSON camelCase (`obsRmsMean`, `obsDim`) is ignored → empty vectors → FATAL.

```
// BAD (export-only / JSON style)
obsDim 19;
obsRmsMean ( … );

// GOOD (see policy/policy_manifest.best_offline_eval2.bak)
obs_dim 19;
obs_rms_mean ( … );
obs_rms_var ( … );
confidence_threshold 0.6;
num_steps 20;
dt_ref 1e-06;
```

---

## 5. Parallel / fields / packing

- **`rl_decisions.csv`**: written to `mesh().time().path()` → under MPI that is **`processorN/`**. Always merge to OUT (see `e17_smoke_run_one.sh`).
- **`solverFlag`**: `uniform 0` / `uniform 1` means **every cell same**, not an empty field.
- Smoke IO: prefer `writeFormat ascii; writeCompression off;` so fields are readable.
- Pack species if you need Y forensics; packing only `T`/`solverFlag`/`chemCpuTime` is insufficient for composition autopsy.
- Write interval vs crash: with `writeInterval=1e-5`, a crash ~4 µs after the last dump leaves **no Y field** of the blow-up — say so in forensics.

### Git

`e17_remote_runs/` is gitignored. Force-add only small reports (`FAILURE_REPORT.md`, `ISSUES.md`, `*summary.json`). Never commit logs, `fields/`, `rl_decisions.csv`, tarballs.

---

## 6. E17.2 chemistry modes (CFD)

| Mode | Meaning |
|------|---------|
| `cvodeOnly` | Force CVODE (Layer-1 sanitize still on) |
| `qssOnly` | **QSS + guards** + CVODE fallback (reported) |
| `rlAdaptive` | **Policy + same guards** |
| stock `solver qss` | **Retired for CFD**; OK for 0D algorithm studies |

Guards (`guardCoeffs`): see `DECISIONS.md` (2026-07-20) and `validation/zeroD/e17_2/E17_2_GATES.md`.

- Fallback windows **count as CVODE** in usage (`solverFlag=0`, `qssFallbackCount++`).
- Keep **`FOAM_SIGFPE` ON** unless the user explicitly waives it.
- No silent “T threshold override” policy hacks for E17.2.
- **LibTorch `LD_PRELOAD`**: required for `reactingFoamDebug` + RL; **aborts** `checkMesh` / `decomposePar` / `reconstructPar` / `foamDictionary` on native QB. Use `env -u LD_PRELOAD …` for utilities (`OFRL_TORCH_PRELOAD=0` in `env.qb.sh`).

---

## 7. Validation scripting hygiene

- Prefer `set -euo pipefail` on the **host**, but **disable `-e` around OpenFOAM bashrc** and around long `docker run` if you need to continue other modes (`02_smoke_three_mode.sh` pattern).
- Always tee docker stdout and record `docker_exit=`; never swallow empty consoles.
- Regex on logs: `re.findall` with **two** groups returns tuples — do not call `.group` on them. Use `finditer` or unpack tuples.
- Env image name: prefer `OF_IMAGE` (smoke kit); accept `OFR_IMAGE` as alias if you add one.

---

## 8. Known campaign facts (do not rediscover blindly)

- Smoke `smoke_20260719_211924`: **cvodeOnly** completed to `5e-4`; **qssOnly** / **rlAdaptive** SIGFPE after ignition (T→3500 = Option R JANAF Thigh). Report: `…/FAILURE_REPORT.md`, `e17_2/FORENSICS.md`.
- At last written time (100 µs), Y looked healthy; blow-up is in the unwritten ~4 µs.
- First 2D load-imbalance datum: cvodeOnly `chemCpuTime` ~**17→432 s** on 3200 cells.

---

## 9. Changelog of footguns (append-only)

| Date | Symptom | Fix / lesson |
|------|---------|----------------|
| 2026-07-20 | `validation/validation/zeroD/...` | `ROOT` depth for `e17_2` scripts = 3×`..` |
| 2026-07-20 | `source: not found` via `/openfoam/run` | `--entrypoint /bin/bash` |
| 2026-07-20 | Silent docker death, empty console | `set +eu` before OF bashrc |
| 2026-07-20 | Foam `fileName` `/` token error on manifest | Quote `"/work/policy/..."` |
| 2026-07-20 | chemFoam ΣY off by ~100 | Use `fractions{}` IC format |
| 2026-07-20 | “Empty” solverFlag / missing CVODE counts | `uniform` compression; merge `processor*/rl_decisions.csv` |
| 2026-07-19 | Policy FATAL host path in container | `E17_CONTAINER_ROOT=/work` |
| 2026-07-20 | Summary `SIGFPE=true` on successful End | Matched FOAM_SIGFPE **trap banner**; require `Signal: Floating point exception` |
| 2026-07-20 | Huge `DILUPBiCGStab: Solving for …` log spam (106 Yi) | `DebugSwitches { SolverPerformance 0; }` in `controlDict` |
| 2026-07-22 | `rl_usage_step.csv` cpu_* looked 8× too large | Those columns are **MPI-sum CPU-seconds** (Σ cell timers over ranks), not wall. After 2026-07-22: CSV has `cpu_*_sum`, `wall_chem` (= max over ranks), `nProcs`. Live run must be restarted to pick up new `librlChemistryModel`. |
| 2026-07-22 | `obs_rms size mismatch mean=0` after `.pt`→`.ts` export | Foam manifest must use `obs_rms_mean` / `obs_dim` (not camelCase). |
| 2026-07-22 | ~90% cells `fallbackCVODE` on E18 RL steps | Counters: **100% `T_bounds`** (fuel T=300 &lt; `TminAccept=310`), not Y/ΣY. Relaxed `epsY=1e-8`, `epsSumY=1e-2`; set `TminAccept=250`. Log `rlFallbackReasons`. |
| 2026-08-20 | `rlUsage` CVODE/QSS disagreed with ParaView `solverFlag` | Usage used `nCvode−nFallback` and fallback **overwrote** `lastDecision` (policy lost). Now: `policyFlag`/`lastDecision` stay policy; `forceCvodeHold` for rescue; log `policyCVODE/QSS` + `effCVODE/QSS`. Trust `solverFlag`=effective, `policyFlag`=policy. |
| 2026-08-20 | JANAF spam `T = 300` out of range 300→3500 | Fuel at Tlow boundary. Set production thermo **`Tlow 200`** (same NASA coeffs; Option R low poly). |
| 2026-08-20 | Huge Foam logs (Yi solvers + warnings) | `logDecisions false` by default; Stage2 awk drops janaf/`Solving for`; `SolverPerformance 0`. |
| 2026-08-20 | `checkMesh`/`decomposePar` **Aborted (core dumped)** on QB | LibTorch `LD_PRELOAD` from `ofrl_container_env.sh`. Run utilities with `env -u LD_PRELOAD …`; keep preload only for `reactingFoamDebug`. |
| 2026-08-20 | Stage1 `exit=141` Broken pipe; awk `Killed` | Progress `awk` in the MPI pipe OOM'd (and/or LibTorch preload on chem-off ranks). Log solver directly; **no** `LD_PRELOAD` for Stage1; sample progress from the log file. |
| 2026-08-20 | `sbatch --parsable` job id garbage on LONI | SU banner lines go to stdout; parse `Submitted job N` / last bare integer. |
| 2026-08-20 | Stage1 Slurm “done” with no progress log | Relative `E18_STAGE1_OUT` + `cd CASE` broke `tee` log path; `env.qb.sh` left `set +e` so sbatch ignored the failure. Use absolute OUT; restore `set -e` after sourcing. |

---

## 10. Quick command cheat sheet

```bash
# E17.2 single-cell QSS vs CVODE (± Y_n2 poison)
bash OPENFOAM_PATH/validation/zeroD/e17_2/e17_2_minimal_repro.sh

# E17.2 guarded 2D: qssOnly → rlAdaptive (no full-mesh cvodeOnly)
bash OPENFOAM_PATH/validation/zeroD/e17_2/e17_2_guarded_rerun.sh

# Configure case mode (writes chemistryProperties + libs)
E17_CONTAINER_ROOT=/work bash OPENFOAM_PATH/validation/zeroD/e17_configure_mode.sh qssOnly
```

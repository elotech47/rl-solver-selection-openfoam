# Production CFD kit (cluster / thesis numbers)

Clean entry point for **thesis-grade** OpenFOAM RL chemistry runs.
Validation campaigns under `validation/zeroD/e*` stay as R&D history — do **not** dump
production fields there.

| Path | Role |
|------|------|
| [`RUN_PLAN.md`](RUN_PLAN.md) | **What to run** on the LSU cluster (priority order) |
| [`scripts/`](scripts/) | Bootstrap, policy, mechanism, case launch, extract |
| [`cluster/`](cluster/) | Slurm/Apptainer stubs for LONI/LSU |
| [`pins/`](pins/) | Frozen case / policy / mechanism versions |
| `runs/` | **Runtime dumps only** (gitignored) |

Canonical Foam tree remains `OPENFOAM_PATH/` (Docker/Apptainer mount ≡ `/work`).

## Quick start (workstation or interactive node)

```bash
cd OPENFOAM_PATH
source production/env.example.sh   # or copy to production/env.local.sh

bash production/scripts/00_bootstrap.sh
bash production/scripts/01_setup_policy.sh   # if policy.ts needs refresh
# mechanism: usually already pinned — see pins/MECHANISM.md

# One mode (recommended on cluster: one job per mode)
export E18_MODES=cvodeOnly
export NPROC=32
bash production/scripts/20_run_chem.sh

# Later: extract small artifacts for laptop analysis
bash production/scripts/30_extract_results.sh production/runs/<run_id>
```

## Design rules

1. **Reuse** E18 Stage-2 chemistry logic (`validation/zeroD/e18_prep/stage2_*`) — wrappers only change **output root** and cluster runtime.
2. **Do not** re-run Stage 0/1 or reconvert the mechanism unless pins change.
3. Commit scripts + small reports; never commit `runs/**` fields/logs.
4. Thesis wall-clock / accuracy numbers come from **this** tree (or tagged cluster dumps), not Mac Docker campaigns (`container/LONI.md`).

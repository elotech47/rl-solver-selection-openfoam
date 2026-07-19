# LONI / HPC port (E17b)

**Goal:** x86_64 Apptainer stack pinned to `validation-baseline-v1` versions;
tag passing environment `hpc-baseline-v1` before any E18 production.

## Status

| Item | Status |
|------|--------|
| Apptainer definition | **DRAFT** — `container/loni-of-rl.def` |
| Build on LONI | **DEFERRED** — waiting on allocation membership |
| Spot re-validation | blocked on build |
| SLURM templates | later, with build |
| Tag `hpc-baseline-v1` | pending green spot set |

## Version pins (match Mac Docker / validation-baseline-v1)

| Component | Pin |
|-----------|-----|
| OpenFOAM | ESI **v2312** (`opencfd/openfoam-default:2312` lineage) |
| SUNDIALS | as in `OPENFOAM_PATH/opt` / container build |
| LibTorch | CPU **2.2.2** wheel lineage (`opt/libtorch`), ABI=0 |
| Mechanism | Option R refit + stock THE |
| QSS | T-freeze ON, epsmin=0.02 |
| Policy | `policy/policy.ts` + `policy_manifest.json` hashes in E16.1 |

## Launch notes (fill when on LONI)

```
# modules / mpi binding — RECORD EXACT LINE HERE after first smoke
# module load ...
# apptainer exec --bind ... loni-of-rl.sif ...
```

Mac workstation results are **not** thesis production numbers (Campaign 5 compute policy).

# LONI Queen Bee — job submission

## Everyday use (one line)

```bash
cd /work/elo/solverRL2D/rl-solver-selection-openfoam/OPENFOAM_PATH
source production/env.qb.sh
```

That loads modules + OpenFOAM-v2312 + LibTorch/SUNDIALS paths. **Do not** reinstall OF each time.

## Stage 1 cold freeze (if `0.05/` missing)

```bash
cd /work/elo/solverRL2D/rl-solver-selection-openfoam/OPENFOAM_PATH
bash production/cluster/submit_stage1.sh
# or: sbatch production/cluster/e18_stage1.sbatch

squeue -u $USER
tail -f production/runs/slurm-*-stage1.out
# solver progress:
tail -f production/runs/stage1_cold_*/progress.coldMix.log
```

When you see `STAGE1_OK`, submit chemistry (smoke / twins).

1. OF-v2312 built under `/work/elo/OpenFOAM/OpenFOAM-v2312`
2. `opt/libtorch` + `opt/sundials` (+ `ln -sfn lib64 opt/sundials/lib` if needed)
3. `bash tools/build_libs.sh` and `wmake` in `applications/solvers/reactingFoam`
4. `policy/policy.ts` + `policy/policy_manifest` present
5. Case freeze: `cases/opposedJet_E18/0.05/`

## Submit jobs (from OPENFOAM_PATH)

```bash
source production/env.qb.sh
# optional smoke first (~2 h wall budget):
sbatch production/cluster/e18_smoke.sbatch

# full twins to endTime=0.059:
bash production/cluster/submit_twins.sh
# or individually:
sbatch production/cluster/e18_cvode.sbatch
sbatch production/cluster/e18_rl.sbatch
sbatch production/cluster/e18_qss.sbatch
```

Watch:

```bash
squeue -u $USER
tail -f production/runs/slurm-*-cvode.out
# progress inside a run dir:
tail -f production/runs/e18_*_cvodeOnly/cvodeOnly/progress.cvodeOnly.log
```

## Account / partition

| Item | Value |
|------|-------|
| Account | `loni_pca_dns` |
| Partition | `single` (≤48 CPUs/node, up to 7 days) |
| Default NPROC | 32 |

Test alloc:

```bash
salloc -A loni_pca_dns -p single -N 1 -n 4 -t 00:10:00
```

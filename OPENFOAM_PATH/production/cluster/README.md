# LONI Queen Bee (QB) — cluster notes

Recon from login node `qbc1` (2026-08-20). Workspace: `/work/elo`.

## Allocation (ACTIVE)

| Item | Value |
|------|-------|
| Account | **`loni_pca_dns`** |
| Remaining SUs | ~2.43e6 / 2.5e6 (expires 2027-07-01) |
| Always pass | `#SBATCH --account=loni_pca_dns` |

Bare `salloc` failed earlier because the default account/partition combo was wrong — not because SUs were zero.

## Disk

| Path | Notes |
|------|-------|
| `/home/elo` | 10 GB quota — code only, not run dumps |
| `/work/elo` | Large work space — **repo + platforms + `production/runs/`** |

## Partitions

| Partition | Use |
|-----------|-----|
| `single` | Default; MaxNodes=1; ≤48 CPUs/node; up to **7 days** — good for long CVODE |
| `workq` / `checkpt` | 3-day max |
| `gpu` / `gpu2` | Not for OF-RL chemistry |

## Runtime: native OpenFOAM (recommended on QB)

**Docker is not required** (and is usually unavailable on LONI). Prefer a **local ESI OpenFOAM v2312** tree under `/work/elo` plus our user libs.

| Approach | Verdict |
|----------|---------|
| Module `openfoam/v2212` / `1912` / `10` | **Do not use** for thesis twins — wrong version vs workstation **2312** |
| Docker on compute nodes | Usually unavailable |
| Apptainer/Singularity SIF of 2312 | Fine if/when available; not required |
| **Native install of ESI 2312 + wmake our stack** | **Preferred** |

What “native” means here:

1. Install/build **OpenFOAM-v2312** (ESI) under e.g. `/work/elo/OpenFOAM/OpenFOAM-v2312` (or vendor tarball + `./Allwmake`).
2. Keep this repo’s `OPENFOAM_PATH` as the **user project** (cases, `src/`, policy, production scripts).
3. After `source …/bashrc`, run `tools/build_libs.sh` (SUNDIALS, LibTorch, QSS/CVODE/RL libs) — same as Docker, without the container.
4. Jobs call `mpirun … reactingFoamDebug -parallel` on the host MPI that matches the OF build.

Parity rule: same **v2312** + same user commit + same pins as workstation. Module v2212 would silently change the instrument.

## Suggested `#SBATCH`

```bash
#SBATCH --partition=single
#SBATCH --account=loni_pca_dns
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --time=3-00:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=3900
```

Test alloc:

```bash
salloc -A loni_pca_dns -p single -N 1 -n 4 -t 00:10:00
```

## One mode per job

```bash
cd /path/to/OPENFOAM_PATH
sbatch production/cluster/e18_cvode.sbatch
sbatch production/cluster/e18_rl.sbatch
sbatch production/cluster/e18_qss.sbatch
```

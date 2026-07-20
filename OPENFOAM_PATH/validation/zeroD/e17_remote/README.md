# E17 remote multi-core run kit

Take the OpenFOAM stack + E17 opposed-jet ignition / three-mode smoke to a
**Linux x86_64** machine (workstation or cluster node) with many cores, run there,
then pull results back for analysis.

**This kit lives at:** `OPENFOAM_PATH/validation/zeroD/e17_remote/`

---

## 0. Prerequisites on the remote machine

| Need | Notes |
|------|--------|
| Docker **or** Apptainer | Image: `opencfd/openfoam-default:2312` (linux/amd64) |
| Git | Clone this repo |
| Python 3.10+ | For preprocess (`numpy`, `matplotlib`) and hot-kernel IC (`cantera` — installed by `00_bootstrap.sh`) |
| Disk | ≥20 GB free (platforms build + case times + logs) |
| RAM | ≥8 GB for 3200-cell CVODE 2D; more if `NPROC` is large |

Mac arm64 Docker works but is slow; **prefer a native linux/amd64 host** for E17.

---

## 1. Push from your laptop (one-time)

This workspace currently has **no `git remote`**. Add GitHub, then push
(include uncommitted E16/E17 work you need on the remote):

```bash
# on Mac, from solver_selection/
cd /path/to/solver_selection
git remote add origin git@github.com:<YOU>/<REPO>.git   # or HTTPS
git status
# commit what you want the remote to see (ask yourself before committing secrets)
git push -u origin main
```

**Not in git (copy separately or reinstall on remote):**

| Artifact | Why | How on remote |
|----------|-----|----------------|
| `OPENFOAM_PATH/opt/sundials*` | large binary | `tools/` install or build via `container/Dockerfile` |
| `OPENFOAM_PATH/opt/libtorch` | large; needed for rlAdaptive | `bash tools/install_libtorch.sh` |
| `OPENFOAM_PATH/policy/*.pt` | often gitignored | `scp` from Mac or from `handoff/checkpoints/` |
| `OPENFOAM_PATH/platforms/` | build products | rebuild with `tools/build_libs.sh` |

`policy/policy.ts` + `policy_manifest*` should be in the repo if tracked; confirm after clone.

---

## 2. Pull and bootstrap on the remote

```bash
git clone git@github.com:<YOU>/<REPO>.git solver_selection
cd solver_selection/OPENFOAM_PATH

# Optional: copy policy checkpoint if missing
# scp user@mac:.../OPENFOAM_PATH/policy/best_offline_eval2.pt policy/

chmod +x validation/zeroD/e17_remote/*.sh tools/*.sh container/of_shell.sh

# Pull OF image
docker pull --platform=linux/amd64 opencfd/openfoam-default:2312

# Bootstrap: SUNDIALS + LibTorch + wmake (inside container)
bash validation/zeroD/e17_remote/00_bootstrap.sh
```

`00_bootstrap.sh` builds user libs/apps into `platforms/linux64GccDPInt32Opt/`.

---

## 3. Run E17 (multi-core)

Default case: `cases/opposedJet_2D`  
Default scout: hot premixed kernel + CVODE (see `01_run_ignition_scout.sh`).

```bash
cd OPENFOAM_PATH

# NPROC = number of MPI ranks (e.g. 8, 16, 32)
export NPROC=16
export E17_END_TIME=0.001          # seconds; raise after ignition proven
export E17_MODE=cvodeOnly          # later: qssOnly | rlAdaptive
export E17_OUT=validation/zeroD/e17_remote_runs/$(date +%Y%m%d_%H%M%S)_${E17_MODE}

bash validation/zeroD/e17_remote/01_run_ignition_scout.sh
```

What the runner does:

1. Applies hot-kernel IC (Z=0.05, T=1300 K) unless `E17_SKIP_KERNEL=1`
2. Writes `decomposeParDict` for `$NPROC`
3. Configures chemistry for `$E17_MODE` (rl stack for qss/rl)
4. `blockMesh` → `decomposePar` → `mpirun -np N reactingFoamDebug -parallel`
5. Reconstructs mesh; copies logs + key fields into `$E17_OUT`

**Three-mode smoke (after ignition BC is proven):**

```bash
for mode in cvodeOnly qssOnly rlAdaptive; do
  export E17_MODE=$mode
  export E17_OUT=validation/zeroD/e17_remote_runs/smoke_${mode}
  export E17_SKIP_KERNEL=1   # keep same IC/BC already on disk
  bash validation/zeroD/e17_remote/01_run_ignition_scout.sh
done
```

For `rlAdaptive`, LibTorch must be present; the script sets `LD_PRELOAD` like E16.

---

## 4. Extract results

On the remote, after a run:

```bash
export E17_OUT=validation/zeroD/e17_remote_runs/<your_run_dir>
bash validation/zeroD/e17_remote/02_extract_results.sh
```

Produces:

- `$E17_OUT/extract/summary.json` — wall time, last Time, max T, FATAL flag
- `$E17_OUT/extract/T_trace.csv` — from log `min/max(T)` / propSanity if present
- `$E17_OUT/extract/bundle.tgz` — logs + summary + control/chemistry copies (portable)

Copy home:

```bash
scp -r user@remote:solver_selection/OPENFOAM_PATH/$E17_OUT/extract ./e17_results_from_remote/
```

---

## 5. Preprocess (local or remote)

```bash
python3 validation/zeroD/e17_remote/03_preprocess.py \
  --run-dir validation/zeroD/e17_remote_runs/<your_run_dir> \
  --out-dir validation/zeroD/e17_remote_runs/<your_run_dir>/preprocess
```

Writes:

- `ignition_gate.json` — PASS/FAIL: max internal T ≫ T_air / kernel T
- `T_vs_time.png` — field max T and propSanity internal max vs time
- `report.md` — short human summary

---

## 6. Suggested SLURM sketch (optional)

```bash
#!/bin/bash
#SBATCH -J e17of
#SBATCH -N 1
#SBATCH -n 16
#SBATCH -t 12:00:00
#SBATCH -o e17_%j.out

module load docker   # or apptainer — site-specific
cd $SLURM_SUBMIT_DIR/OPENFOAM_PATH
export NPROC=${SLURM_NTASKS}
export E17_OUT=validation/zeroD/e17_remote_runs/slurm_${SLURM_JOB_ID}
bash validation/zeroD/e17_remote/01_run_ignition_scout.sh
bash validation/zeroD/e17_remote/02_extract_results.sh
```

Apptainer: see `container/LONI.md` + `container/loni-of-rl.def` (E17b; deferred until allocation).

---

## 7. Success criteria (E17.1 ignition)

| Check | Pass |
|-------|------|
| No `FOAM FATAL` | required |
| Run reaches `endTime` or clear runaway | required |
| max **internal** T ≫ air BC / kernel T (e.g. >1600 K) | ignition |
| propSanity ~1e-14 | sanity |

Then proceed to qssOnly + rlAdaptive on the **same** BC/IC.

---

## Files in this kit

| File | Role |
|------|------|
| `00_bootstrap.sh` | Image + SUNDIALS/LibTorch + wmake |
| `01_run_ignition_scout.sh` | Parallel OF run |
| `02_extract_results.sh` | Pack logs/metrics |
| `03_preprocess.py` | Plots + ignition gate |
| `decomposeParDict.template` | MPI domain split |
| `README.md` | This document |

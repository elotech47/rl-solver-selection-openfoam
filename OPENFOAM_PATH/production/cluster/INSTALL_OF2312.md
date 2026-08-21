# Install ESI OpenFOAM **v2312** on LONI Queen Bee (native)

Workstation parity target: ESI **v2312** (same lineage as `opencfd/openfoam-default:2312`).
Do **not** use module `openfoam/v2212` for thesis twins.

Home quota is only **10 GB** — install under **`/work/elo`**.

---

## 0. One-time layout

```bash
# On login node qbc1
mkdir -p /work/elo/OpenFOAM /work/elo/src
cd /work/elo/OpenFOAM
```

Expected after install:

```text
/work/elo/OpenFOAM/
  OpenFOAM-v2312/
  ThirdParty-v2312/
```

Your RL project (this repo’s `OPENFOAM_PATH`) stays separate, e.g.:

```text
/work/elo/solver_selection/OPENFOAM_PATH/   # or clone of rl-solver-selection-openfoam
```

---

## 1. Get a build node (do **not** compile on the login node)

```bash
salloc -A loni_pca_dns -p single -N 1 -n 32 -t 08:00:00 --mem-per-cpu=3900
# wait until you land on a compute node, then:
hostname   # should be qbcNNN, not qbc1
```

All compile steps below run **inside this allocation**.

---

## 2. Load a toolchain (pick one stack and stick to it)

**Recommended first try (GCC + OpenMPI):**

```bash
module purge
module load gcc/13.2.0
module load openmpi/4.0.3/intel-19.0.5   # if this exact name fails, use: module avail openmpi
# optional helpers:
module load cmake/3.27.7/gcc-8.5.0 2>/dev/null || module load cmake/3.18.4/gcc-9.3.0
which mpicc mpicxx
mpicc -showme:version 2>/dev/null || mpicc -v | head -1
```

**Alternative (Intel MPI)** — only if you prefer it and set `WM_MPLIB` accordingly:

```bash
module purge
module load gcc/13.2.0          # or intel/19.0.5 if you go full Intel
module load intel-mpi/2021.5.1
```

Record the exact `module list` in a file — jobs must reload the **same** modules.

```bash
module list 2>&1 | tee /work/elo/OpenFOAM/MODULES_USED.txt
```

---

## 3. Download sources (login or compute; needs network)

Official packs ([openfoam.com release history](https://www.openfoam.com/download/release-history)):

```bash
cd /work/elo/OpenFOAM
wget https://dl.openfoam.com/source/v2312/OpenFOAM-v2312.tgz
wget https://dl.openfoam.com/source/v2312/ThirdParty-v2312.tgz

# optional checksums (from OpenCFD):
# OpenFOAM-v2312.tgz   md5 da71a03f29bf731152a071eaafc056d9
# ThirdParty-v2312.tgz md5 fafa6d21a8e876eecc0e1a9dc15db12f
md5sum OpenFOAM-v2312.tgz ThirdParty-v2312.tgz

tar -xzf OpenFOAM-v2312.tgz
tar -xzf ThirdParty-v2312.tgz
ls   # must show OpenFOAM-v2312  and  ThirdParty-v2312  as siblings
```

If `wget` is blocked on compute nodes, download on login node (same paths), then `salloc`.

---

## 4. Point OpenFOAM at system MPI (important on HPC)

```bash
cd /work/elo/OpenFOAM/OpenFOAM-v2312

# Create prefs (do not edit bashrc by hand)
mkdir -p etc
cat > etc/prefs.sh <<'EOF'
# Queen Bee — use site MPI, not ThirdParty OpenMPI
export WM_COMPILER=Gcc
export WM_MPLIB=SYSTEMOPENMPI
# If you chose Intel MPI instead:
# export WM_MPLIB=INTELMPI
EOF
```

If `SYSTEMOPENMPI` fails at link time, try `SYSTEMMPI` and set:

```bash
export MPI_ROOT="$(dirname "$(dirname "$(which mpicc)")")"
```

before sourcing bashrc (details vary by LONI module layout).

---

## 5. Source environment and smoke-check

```bash
cd /work/elo/OpenFOAM/OpenFOAM-v2312
set +eu
source ./etc/bashrc
set -e
set +u

echo "WM_PROJECT_DIR=$WM_PROJECT_DIR"
echo "WM_OPTIONS=$WM_OPTIONS"
echo "FOAM_LIBBIN=$FOAM_LIBBIN"
which wmake
foamEtcFile -list 2>/dev/null | head -3 || true
```

You should see `platforms/linux64GccDPInt32Opt` (or similar) under the project dir after the build.

**Do not** build ParaView inside ThirdParty for this project (huge, unused). Stock `Allwmake` is enough for solvers.

---

## 6. Compile (1–several hours on 32 cores)

```bash
cd /work/elo/OpenFOAM/OpenFOAM-v2312
./Allwmake -j 32 -s -l
# log file: log.linux64GccDPInt32Opt (name depends on WM_OPTIONS)
```

If the allocation is about to expire, stop cleanly and later:

```bash
salloc ...   # new node, same modules
source /work/elo/OpenFOAM/OpenFOAM-v2312/etc/bashrc
cd /work/elo/OpenFOAM/OpenFOAM-v2312
./Allwmake -j 32 -s -l    # resumes; already-built targets are skipped
```

### Sanity check

```bash
source /work/elo/OpenFOAM/OpenFOAM-v2312/etc/bashrc
which blockMesh decomposePar reactingFoam
blockMesh -help | head -5
echo "OK — core OpenFOAM v2312 is installed"
```

---

## 7. Wire our RL project to this install

```bash
# every job / shell:
module purge
module load gcc/13.2.0
module load openmpi/...          # SAME as MODULES_USED.txt
source /work/elo/OpenFOAM/OpenFOAM-v2312/etc/bashrc

export OF_BASHRC=/work/elo/OpenFOAM/OpenFOAM-v2312/etc/bashrc
export OF_RUNTIME=native

cd /path/to/OPENFOAM_PATH        # this repo
source tools/ofrl_container_env.sh   # sets FOAM_USER_* ; may need small path tweaks on native
bash tools/build_libs.sh             # QSS + CVODE + RL + apps  (after SUNDIALS/LibTorch)
```

Third-party for **our** stack (not OF’s ThirdParty):

| Piece | How |
|-------|-----|
| SUNDIALS | as in `tools/` / existing `opt/` docs |
| LibTorch CPU | `tools/install_libtorch.sh` (or copy from workstation) |

Production env pin:

```bash
# in production/env.local.sh (gitignored)
export OF_BASHRC=/work/elo/OpenFOAM/OpenFOAM-v2312/etc/bashrc
export OF_RUNTIME=native
export SLURM_ACCOUNT=loni_pca_dns
```

---

## 8. Common failures

| Symptom | Fix |
|---------|-----|
| `salloc` invalid account | Always `-A loni_pca_dns` |
| Compile on `qbc1` login | Use `salloc` compute node |
| Home disk full | Install only under `/work/elo` |
| MPI link errors | Match `WM_MPLIB` to the module you loaded; rebuild after changing prefs |
| `openfoam/v2212` module | Unload it; never mix with this tree |
| bashrc + `set -e` dies | `set +eu` before `source …/bashrc` (`AGENTS.md`) |

---

## 9. After OF is green — next messages to me

Paste:

```bash
source /work/elo/OpenFOAM/OpenFOAM-v2312/etc/bashrc
echo WM_PROJECT_VERSION=$WM_PROJECT_VERSION
echo WM_OPTIONS=$WM_OPTIONS
which reactingFoam
module list 2>&1
du -sh /work/elo/OpenFOAM
```

Then we can patch `production/scripts` for true native launch (source `$OF_BASHRC` instead of Docker paths) and run the E18 bootstrap.

---

## Appendix — LibTorch / SUNDIALS on QB (no Docker)

```bash
# Inside salloc; do NOT leave set -e on in the interactive shell (a failed
# command can kill the whole allocation). Prefer:
set +e

cd /work/elo/solverRL2D/rl-solver-selection-openfoam/OPENFOAM_PATH
bash tools/install_libtorch.sh      # RHEL8: ABI=0 pip (cxx11 zip needs glibc 2.29)
# QB RL:
#   LIBTORCH_FORCE=1 LIBTORCH_CXX11_ABI=0 bash tools/install_libtorch.sh
#   bash tools/build_ofrl_policy_worker.sh && wmake -j8 src/policyRuntime
module load cmake/3.27.7/gcc-8.5.0  # if needed
bash tools/install_sundials.sh

set +eu
source /work/elo/OpenFOAM/OpenFOAM-v2312/etc/bashrc
set +u
source tools/ofrl_container_env.sh
bash tools/build_libs.sh
```

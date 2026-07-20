# Pinned toolchain versions

| Component | Version | Notes |
|-----------|---------|-------|
| OpenFOAM (ESI) | **v2312** | Image `opencfd/openfoam-default:2312` |
| Base OS (container) | Ubuntu (image default) | amd64; Apple Silicon via Docker QEMU |
| SUNDIALS / CVODE | ≥ 6.x | Installed in custom Dockerfile layer |
| LibTorch (CPU) | **2.2.2** (pip `torch` cpu wheel → `opt/libtorch`) | **linux/amd64** on WSL Threadripper; **linux/arm64** on Mac. `_GLIBCXX_USE_CXX11_ABI=0`. Install: `OF_PLATFORM=linux/amd64 bash tools/install_libtorch.sh`. |
| Cantera (host oracle) | ≥ 3.0 | `rlEnv` / handoff dependency |
| PyTorch (host export) | 2.x | Policy `.pt` → TorchScript export |
| qss-integrator | research C++ CHEMEQ2 | Host oracle via handoff |
| Mechanism | Luo n-dodecane YAML | SHA256 in `mechanisms/n-dodecane.yaml.sha256` |
| Policy checkpoint | `best_offline_eval2.pt` | 19-D state+grads; obs_rms in checkpoint |
| handoff package | `solver_selection_handoff` | `pip install -e ../handoff` |

## Decision cadences / solver defaults

- Chemistry micro-window: `1e-6` s (`maxChemDeltaT`)
- Policy re-query every τ_dec = `num_steps × dt_ref` of chemistry time (E16.5; not CFD micro-window count)
- CVODE: `rtol=1e-8`, `atol=1e-12`, BDF + Newton + dense FD Jacobian
- QSS: `epsmin=0.02`, `epsmax=100`, `dtmin=1e-12`, `dtmax=1e-6`, `abstol=1e-11`, `itermax=2`
- Confidence floor: `0.6` → force CVODE

## x86_64 (WSL Threadripper / E17)

- Docker: `opencfd/openfoam-default:2312` with `--platform=linux/amd64`
- SUNDIALS: `opt/sundials` (not `sundials-arm64`)
- LibTorch: `OF_PLATFORM=linux/amd64 bash tools/install_libtorch.sh`
- MPI: `mpirun -np 16 --map-by core --bind-to core` (16 physical cores; do not use 32 logical)
- Thread hygiene: `OMP_NUM_THREADS=1`, `ATEN_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `TORCH_MKLDNN_ENABLED=0`
- **LD_PRELOAD**: on amd64, preload `libtorch_cpu.so` + `libc10.so` + first `libomp*.so` if present (see `tools/ofrl_container_env.sh`). No arm64-specific MKLDNN workaround required on x86_64 in initial E17 runs.

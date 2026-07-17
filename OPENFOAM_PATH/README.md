# of-rl-chem (OpenFOAM RL adaptive chemistry)

ESI OpenFOAM **v2312** extensions: CVODE + α-QSS (CHEMEQ2) chemistry solvers with
zero-shot RL policy dispatch. Spec: [`instruction.md`](instruction.md).

## Quick start (Mac + Docker)

```bash
# 1. Base image (already pulled if Phase 0 ran)
docker pull opencfd/openfoam-default:2312

# 2. Optional: build image with SUNDIALS + LibTorch
docker build -t of-rl-chem:2312 -f container/Dockerfile .

# 3. Interactive OpenFOAM shell (repo mounted at /work)
./container/of_shell.sh
```

Host-side Python oracles (rate/step/policy parity):

```bash
workon rlEnv   # or any env with cantera+torch
pip install -e ../handoff
python validation/rate_parity/run_rate_parity.py --n-states 50
python tools/export_policy.py
```

## Layout

See `instruction.md` §1. Versions: `VERSIONS.md`. Decisions: `DECISIONS.md`.

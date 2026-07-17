# opposedJet_2D — status

## Goal
Planar opposed-jet with Luo n-dodecane; compare CVODE / QSS / RL.

## What works now
- Local **`reactingFoamDebug`** with mass-weighted h→T (H6 fix) in `EEqn.H`
- Case bootstrapped from ESI `counterFlowFlame2D` + Luo foam mechanism
- Species BCs: `nc12h26` (fuel), `n2`/`o2` (air); T fuel 300 K / air 1100 K
- **Smoke:** `endTime=2e-5` completes (`log.reactingFoam`), `min/max(T)=300,1100`, no Newton abort

## Run
```bash
# inside of_shell / arm64 container with FOAM_USER_* pointing at this repo
cd cases/opposedJet_2D
blockMesh
reactingFoamDebug
```

## Not yet
- Full autoignition to steady flame / strain sweep
- Solver-map postprocessing vs centerline Ember
- `coflow_2D` still scaffold-only

# Phase 0–3 implementation status

## Done this session (libraries)

| Item | Status |
|------|--------|
| `libqssChemistrySolver.so` | Built; chemFoam selects `solver qss` |
| `libcvodeChemistrySolver.so` | Built (SUNDIALS 6.7 in `opt/sundials`); chemFoam selects `solver cvode`, non-zero Qdot |
| SUNDIALS | Installed to `OPENFOAM_PATH/opt/sundials` (workspace mount; custom Docker image deferred — QEMU/apt flaky) |
| Build helper | `tools/build_libs.sh` |

## Known issues before full 0D vs handoff compare

1. **chemFoam pressure** still shows tutorial leftover `~1.37e6` Pa in logs despite `initialConditions` at 10 atm — fix `0/p` / IC path.
2. **QSS short smoke** reported `Qdot = 0` (CVODE did not) — debug composition/ω assembly before declaring QSS physics-ready.
3. Full ignition-delay runs (+ handoff compare) not started yet.

## How to rebuild / run

```bash
# Inside Docker (./container/of_shell.sh or --entrypoint bash):
export FOAM_USER_LIBBIN=$PWD/platforms/linux64GccDPInt32Opt/lib
export SUNDIALS_DIR=$PWD/opt/sundials
export LD_LIBRARY_PATH=$SUNDIALS_DIR/lib:$FOAM_USER_LIBBIN:$LD_LIBRARY_PATH
./tools/build_libs.sh

cd cases/chemFoam_0D
# set chemistryType.solver to qss or cvode in constant/chemistryProperties
chemFoam
```

## Next

1. Fix IC pressure / Y path for MidT_MidP
2. Debug QSS Qdot=0
3. Long chemFoam runs to ignition vs `solver-selection-eval` (handoff)

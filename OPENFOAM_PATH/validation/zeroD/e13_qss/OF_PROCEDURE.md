# E13.1 OpenFOAM procedure (blocked on manual Docker run)

Python-QSS reference is produced by `e13_1_qss_step.py`. OF comparison requires
identical `(Y,T,p)` and QSS controller settings (`epsmin=0.02`, `epsmax=100`,
`dtmin=1e-12`, `dtmax=1e-6`, `abstol=1e-11`, `itermax=2`).

## Generated artifacts

| Path | Purpose |
|------|---------|
| `of_ic/<tag>/initialConditions` | Mass-fraction IC for chemFoam_0D |
| `of_ic/<tag>/e8_crash_state.dat` | E8-style Y dump (reference) |
| `py_qss_step_<tag>.npz` | Python ΔY, ΔT after 1 µs |

Tags: `T1301`, `T1500`, `T1701`, `T2001` (rounded from pinned T).

## Docker commands (exact)

```bash
# Host: ensure Python reference exists
cd OPENFOAM_PATH/validation/zeroD
/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python e13_1_qss_step.py

# Container
./container/of_shell.sh
cd validation/zeroD
chmod +x run_e13_1_of.sh
./run_e13_1_of.sh all
# Or one state:
./run_e13_1_of.sh T1301

# Re-compare on host
/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python e13_1_qss_step.py
```

## Expected OF outputs

- `e13_qss/of_runs/<tag>/chemFoam.out` — two lines: t=0 and t=1e-6 with T
- `e13_qss/of_runs/<tag>/e8_state.csv` — per-step diagnostics (Tprev, hsSum, …)
- Post-step Y: read `cases/chemFoam_0D/0/<time>/Y*` if writeInterval fires; else
  extend `debugStateDump.H` to emit post-step Y (not yet wired for arbitrary pin).

## Parity metrics

- Primary: `ΔT` after 1 µs (Python in `e13_1_summary.json`)
- Secondary: `max|ΔY|` — OF side pending field dump
- Gate (provisional): `|ΔT_OF − ΔT_Py| / |ΔT_Py| ≤ 1%` at each pin

## Known limitation

chemFoam has no native “load e8_crash_state.dat and stop” API. Mass-fraction
`initialConditions` is the supported path. Single-step timing requires
`endTime=deltaT=1e-6` override in `run_e13_1_of.sh`.

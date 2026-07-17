# 2D coflow diffusion flame (Case B)

## Configuration

- Planar or axisymmetric laminar coflow
- Gaseous n-dodecane jet into hot air coflow (900–1100 K sweep)
- Mesh: 30–60k (iterate) → 100–200k production
- Chemistry windows ~1 µs via `maxChemDeltaT` + CFD Δt

## Runs (identical mesh/Δt/tolerances)

1. `cvodeOnly` — reference
2. `qssOnly` — expect delayed/failed ignition signature
3. `rlAdaptive` — solver maps + speedup

## Metrics

See `analysis/metrics.py`. Export `solverFlag`, chem CPU, T/OH fields.

## Status

Scaffold only; generate mesh + boundary dictionaries after Phase 1 gates pass.

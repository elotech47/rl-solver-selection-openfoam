# E17.1 — Ignition scout (opposed-jet CVODE)

## Attempt A — T_air=1350 K, U=±0.05 (mixing only)
**STOPPED** at t≈0.62 ms: max internal T≈937 K (no runaway). Same pattern as E12.
See `scout_partial.json`.

## Attempt B — hot premixed kernel (IN PROGRESS)
Internal field: **Z=0.05, T=1300 K, p=10 atm** (Cantera mix); fuel/air BCs unchanged
(T_air=1350, U=±0.05). `endTime=1 ms`. Goal: thermal runaway from hot premix under strain.

Gate: max internal T ≫ 1300 K (and ≫ T_air), no FATAL.

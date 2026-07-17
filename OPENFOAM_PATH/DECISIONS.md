# Design decisions log

| Date | Decision | Justification |
|------|----------|---------------|
| 2026-07-15 | Use ESI OpenFOAM **v2312** (not Foundation OF11) | Spec requires templated `StandardChemistryModel` / `chemistrySolver` hierarchy and DLBFoam compatibility |
| 2026-07-15 | Develop on Mac via Docker bind-mount | OpenCFD images are linux/amd64; Mac runs under Docker Desktop emulation |
| 2026-07-15 | Mechanism from `handoff` packaged `n-dodecane.yaml` | Single source of truth matching 0D eval; avoid Pele Lu-53 |
| 2026-07-15 | Policy from `best_offline_eval2.pt` | Production CnF / handoff paper checkpoint (19-D) |
| 2026-07-15 | Port CHEMEQ2 from Pele `qss_int` (std::vector, no AMReX) | Algorithm already patched for true q/d; integrate into ESI chemistrySolver |
| 2026-07-15 | Chemistry integrates const-P composition + T from energy in cell ODE; OF couples via effective RR | Match 0D training (const-P) as closely as ESI RR interface allows; log T-consistency diagnostic |
| 2026-07-15 | `maxChemDeltaT=1e-6`, policy every 20 sub-windows | Match handoff `num_steps=20` at `dt=1e-6` |
| 2026-07-15 | LibTorch CPU for batched policy inference | Matches paper CPU inference; avoid GPU under MPI complexity on workstation |
| 2026-07-15 | chemkinToFoam needs OF `transportProperties` dict (not Chemkin tran.dat) | ESI tutorial / Allrun convention; Cantera `tran.dat` rejected by Foam lexer |
| 2026-07-15 | Rewrite Cantera thermo → 80-col CHEMKIN-II (`therm_of.dat`) | Cantera headers (`G300.000`) break OpenFOAM chemkinReader |
| 2026-07-15 | ELEMENTS one-per-line; `REACTIONS CAL/MOLE` only | Fixes ESI chemkinLexer parse of yaml2ck output |
| 2026-07-15 | Docker `--entrypoint /bin/bash` | Image entrypoint `/openfoam/run` breaks nested bash quoting |
| 2026-07-15 | MidT Python QSS slower than CVODE in one spot-check | Binding/config overhead possible; keep profiling gate when OF port is timed |

# E17.2 minimal repro — interpreted results (celli 2607)

All four `chemFoamDebug` cases **End** with exit 0. Guards ON. FOAM_SIGFPE trap banner is **not** a crash (summary previously false-flagged it).

## Table (from `chemFoam.out` + fields at `1e-06`)

| Case | T₀ [K] | T₁ [K] | ΔT [K] | yClipMass | qssFallbackCount | solverFlag |
|------|-------:|-------:|-------:|----------:|-----------------:|-----------:|
| cvode_clean | 2507.66 | 2582.93 | **+75.3** | 0 | 0 | 0 (CVODE) |
| qss_clean | 2507.66 | 2582.70 | **+75.0** | 0 | 0 | 1 (QSS) |
| cvode_Yn2neg | 2507.66 | 3073.87 | **+566.2** | **1e−4** | 0 | 0 |
| qss_Yn2neg | 2507.66 | 3073.87 | **+566.2** | **1e−4** | **1** | **0** |

## What this proves

1. **Clean near-front cell:** QSS and CVODE agree to ~0.2 K over one 1 µs window — stack is healthy.
2. **Guards fire on poisoned IC:** Layer-1 records `yClipMass=1e−4`. Layer-2 **rejects QSS** once (`qssFallbackCount=1`) and redos with CVODE → `solverFlag=0`, **bit-same T₁ as cvode_Yn2neg**.
3. **Large ΔT on Yn2neg is mostly composition change, not “QSS gone wild”:** `poison_n2` sets `Y_n2=-1e-4` and **moves former N₂ mass into other species** so ΣY=1 for chemFoam. After clip, the cell is essentially **undiluted** → both integrators heat ~566 K. CVODE and post-fallback QSS match.

## What this does *not* yet prove

Unguarded QSS seeing a **small negative Y on an otherwise identical mixture** (the original hypothesis). That needs a separate ablation (`guardCoeffs.enabled false` **and** no entry floor / chemFoam renorm caveats — see `AGENTS.md`). Production path floors negatives before the ODE.

## Bottom line for E17.2

Guarded QSS behaved as designed: **detect → CVODE fallback → no free QSS rescue in usage metrics.** Proceed to guarded 2D rerun.

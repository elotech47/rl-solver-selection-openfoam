# E17.2 — QSS robustness under transport: gates & interpretation

## Modes (CFD)

| Mode | Meaning after E17.2 |
|------|---------------------|
| `cvodeOnly` | Force CVODE; Layer-1 sanitize still on |
| `qssOnly` | **QSS + guards** (CVODE fallback reported) |
| `rlAdaptive` | **Policy + same guards** |
| stock `solver qss` | **Retired for CFD**; still valid for 0D algorithm studies |

## Guard dictionary (`guardCoeffs`) — recorded values

| Key | Value | Role |
|-----|------:|------|
| `enabled` | true | master switch |
| `epsY` | 1e-8 | reject if any Y_i &lt; −epsY (was 1e-12; too tight on raw CHEMEQ2) |
| `epsSumY` | 1e-2 | reject if \|ΣY−1\| &gt; epsSumY (was 1e-3) |
| `dTmaxWindow` | 500 K | reject if \|ΔT\| per chem micro-window exceeds |
| `TminAccept` | 250 K | reject below (was 310; E18 fuel inlet is 300 K) |
| `TmaxAccept` | 3400 K | reject above (below JANAF Thigh=3500) |

Layer 1 always floors Y≥0 and renorms ΣY=1 before the integrator; clipped negative mass accumulates in `yClipMass`.  
Layer 2 reject → restore state → CVODE redo → `qssFallbackCount++`; **`solverFlag=0`** for that window (no free rescue in usage).

FOAM_SIGFPE stays **ON**. No policy changes. No T-threshold policy overrides.

## Rerun sequence

```bash
# After code pull — rebuild happens inside smoke docker, or:
#   docker ... wmake src/rlChemistryModel

# Guarded qssOnly then rlAdaptive (reuse cvodeOnly from smoke_20260719_211924 if desired)
export E17_MODES="qssOnly rlAdaptive"
export E17_SKIP_KERNEL=1 E17_END_TIME=5e-4 NPROC=16
export E17_SMOKE_OUT=validation/zeroD/e17_remote_runs/e17_2_guarded_$(date +%Y%m%d_%H%M%S)
bash validation/zeroD/e17_remote/02_smoke_three_mode.sh
```

Minimal Y_n2 poison proof (after rebuild):

```bash
bash validation/zeroD/e17_2/e17_2_minimal_repro.sh
```

## Gates

| Gate | Criterion |
|------|-----------|
| Complete | both modes reach `endTime=5e-4`, `End`, no SIGFPE |
| Temperature | Tmax ≲ 2850 K (adiabatic + margin); must not stick at 3500 |
| Fallback report | `qssFallbackCount` field + `e17_2_usage.json`; spatial map at flame |
| Accuracy | rlAdaptive vs cvodeOnly ~10 K class on T |
| Overhead | unchanged relative to prior E17 cost gate |
| SIGFPE | remains enabled |

## Interpretation fork (post-rerun)

Let  
- \(f_\mathrm{fb}^\mathrm{qss}\) = fallback-window fraction in guarded qssOnly  
- \(f_\mathrm{CVODE}^\mathrm{rl}\) = CVODE-equivalent usage in rlAdaptive (policy CVODE **+** fallbacks)

**Thesis-positive:** \(f_\mathrm{CVODE}^\mathrm{rl} \ll f_\mathrm{fb}^\mathrm{qss}\) → policy adds value beyond the safety net.  
**Adaptation trigger:** fallback dominates flame cells regardless of policy → log in `THESIS_NOTES` as post-E18 in-situ fine-tuning trigger.

## Forensics status

See `validation/zeroD/e17_2/FORENSICS.md`. Write-time Y healthy through 100 µs; crash in unwritten ~4 µs; T=3500 = Option R Thigh; cvodeOnly chemCpu **16.8→432 s**.

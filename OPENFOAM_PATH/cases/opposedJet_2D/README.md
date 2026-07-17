# 2D planar opposed-jet (rung d) — scaffolding

## Goal

Reproduce Ember 1D counterflow as 2D planar opposed-jet:
- Fuel: n-dodecane vapor at 300 K
- Air: 800 K
- Start strain rate ~500 s⁻¹ (span 10–2000 later)
- RL-adaptive vs cvodeOnly / qssOnly

## Mesh

Structured half-domain along jet axis; refine flame zone. Start ~30–50k cells.

## chemistryProperties

```
rl
{
    mode                rlAdaptive; // cvodeOnly | qssOnly | rlAdaptive
    maxChemDeltaT       1e-6;
    numSteps            20;
    confidenceThreshold 0.6;
    torchScript         "policy.ts";
    manifest            "policy_manifest.json";
}
```

## Acceptance

Centerline T RMSE ≲ 10 K vs OF-CVODE; CVODE band at reaction zone; report speedup.

## Status

Case dictionaries to be finalized after stock chemFoam mechanism import succeeds.
Copy reactingFoam tutorial and replace BC/mechanism when ready.

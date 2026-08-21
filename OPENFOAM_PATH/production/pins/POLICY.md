# Policy pin — production CFD

| Item | Value |
|------|-------|
| Checkpoint | `lambda_1p0_with_base_obs_rms.pt` (handoff / local `policy/`) |
| Export | `tools/export_policy.py` → `policy/policy.ts` |
| Foam manifest | `tools/export_policy_manifest_foam.py` → `policy/policy_manifest` |
| Keys | **snake_case** only: `obs_dim`, `obs_rms_mean`, `obs_rms_var`, … |
| Defaults | `num_steps=20`, `dt_ref=1e-6` → τ_dec = 2×10⁻⁵ s |
| Confidence | threshold 0.6 → force CVODE |

Refresh:

```bash
bash production/scripts/01_setup_policy.sh /path/to/lambda_1p0_with_base_obs_rms.pt
```

Record SHA256 of `policy.ts` + `policy_manifest` in each run’s `MANIFEST.txt`.

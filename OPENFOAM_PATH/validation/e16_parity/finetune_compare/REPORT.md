# Finetune policy compare (MidT 0D, teacher-forced on CVODE)

Horizon **t_end=3.5e-3** (through ignition), dt=1e-6, num_steps=20, τ_dec=2e-5 s.

Finetunes are bare `state_dict`s; **base `obs_rms` injected** from `best_offline_eval2.pt`.

## Selection (teacher-forced)

| Policy | n | CVODE% | QSS% | mean conf | OOD% | agree vs base |
|---|---:|---:|---:|---:|---:|---:|
| base | 175 | 8.0 | 92.0 | 0.817 | 2.9 | 100.0% |
| lambda_1p0 | 175 | 66.3 | 33.7 | 0.700 | 9.1 | 40.6% |
| lambda_init_1p0 | 175 | 49.1 | 50.9 | 0.621 | 49.1 | 54.3% |
| finetuned_1D_policy6 | 175 | 99.4 | 0.6 | 0.989 | 0.0 | 7.4% |
| lambda_1p0_NO_obs_rms | 175 | 14.9 | 85.1 | 0.692 | 6.3 | 92.0% |

## Phase CVODE% (bins on base-trajectory T)

| Policy | T&lt;1500 | 1500–2200 | T≥2200 |
|---|---:|---:|---:|
| base | 12% | 0% | 0% |
| lambda_1p0 | 49% | 100% | 100% |
| lambda_init_1p0 | 75% | 0% | 0% |
| finetuned_1D_policy6 | 99% | 100% | 100% |
| lambda_1p0_NO_obs_rms | 21% | 100% | 2% |

## Takeaways

1. **Base obs_rms is usable** with these finetunes: same 19-D arch; wrapping restores nonzero rms.
2. **Without obs_rms**, `lambda_1p0` collapses toward base-like QSS-heavy behavior (agree 92% with base) — do not deploy bare.
3. With base obs_rms, all three finetunes use **more CVODE** than base (esp. `finetuned_1D_policy6` ≈99%).
4. The three finetunes are **not identical**: `lambda_1p0` ~66% CVODE, `lambda_init=1.0` ~49%, `policy6` ~99%.

Artifacts: `validation/e16_parity/finetune_compare`

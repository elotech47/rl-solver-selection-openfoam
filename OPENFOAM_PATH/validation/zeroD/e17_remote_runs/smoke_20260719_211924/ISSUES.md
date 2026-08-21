# E17 smoke issues (20260719_211924)

## 1. CVODE fields looked unreadable
Cause: `writeFormat binary` (+ compression). IDE shows binary blob.
Fix applied:
- Converted times `0.0002`–`0.0005` to ASCII under `cvodeOnly/fields_ascii/`
- Smoke kit now defaults to `writeFormat ascii; writeCompression off;`

Readable summary (fields_ascii):
| t [s] | Tmin | Tmax | chemCpu min | chemCpu max |
|------:|-----:|-----:|------------:|------------:|
| 0.0002 | 918 | 2824 | 8.6 | 392 |
| 0.0003 | 853 | 2789 | 11.8 | 408 |
| 0.0004 | 814 | 2786 | 14.4 | 420 |
| 0.0005 | 783 | 2786 | 16.9 | 432 |

cvodeOnly wall ≈ 20253 s (~5.6 h), exit 0, End at t=5e-4.

## 2. QSS crashed — RL never started
qssOnly ignited (~t=1.02e-4, T→2700 K) then T clipped at 3500 K, cp blew up (~12k), then **SIGFPE (exit 136)** in `PBiCGStab` during species solve at t≈1.0415e-4. wall_s=83.

Campaign used `set -e`, so docker failure aborted the loop → **rlAdaptive never launched**.

Smoke kit fixed to continue remaining modes after a failure.
Resume RL with:
```bash
export E17_SMOKE_OUT=validation/zeroD/e17_remote_runs/smoke_20260719_211924
export E17_MODES=rlAdaptive NPROC=16 E17_END_TIME=5e-4 E17_SKIP_KERNEL=1
bash validation/zeroD/e17_remote/02b_smoke_resume.sh
```

## 3. rlAdaptive: “empty” solverFlag + no CVODE/QSS counts
`solverFlag` was **not empty**. OpenFOAM compresses identical values to `uniform 0` / `uniform 1`:
- t ≤ 4e-5: all CVODE (`uniform 0`) — before / early τ_dec
- t ≥ 5e-5: all QSS (`uniform 1`) at every field dump

`rl_decisions.csv` was written under **`processor*/`** (parallel `time().path()`), not case root, so the smoke packer never copied it. Merged now into `rlAdaptive/rl_decisions.csv` + `rl_usage_summary.json`.

| Metric | Value |
|--------|------:|
| decisions logged | 19200 |
| CVODE (flag=0) | 6437 (33.5%) |
| QSS (flag=1) | 12763 (66.5%) |
| mean conf | 0.88 |

Per CFD decision epoch (all 3200 cells):
| t [s]               | CVODE | QSS  |
| --------------------:| ------:| -----:|
| 1e-5, 3e-5          | 3200  | 0    |
| 5e-5 … 8.3e-5       | 0     | 3200 |
| ~1.01e-4 (ignition) | 37    | 3163 |

Crash (wall ≈ 221 s, exit 136): same post-ignition path as qssOnly — T→3500, then CVODE `h→1e-78` / SIGFPE in `omega` while building Jacobian. Policy was ≈99% QSS into the blow-up.

Packer now merges `processor*/rl_decisions.csv` on future runs (`e17_smoke_run_one.sh`). Post-parse bug (`findall` + `.group`) fixed in `e17_smoke_post_one.py`.

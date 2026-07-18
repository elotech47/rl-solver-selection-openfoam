# E13 — QSS parity on Option R refit thermo

**Thermo:** `mechanisms/refit/n-dodecane_refit.yaml` + foam in `mechanisms/foam/`  
**Parity target:** Python-QSS (handoff), not CVODE  
**Context:** Prior OF-QSS was early (−9.6% vs Py-CVODE on full MidT); E13 isolates single-step QSS at pinned high-T states.

---

## E13.1 — Single 1 µs QSS step at pinned states

### Status: Python **DONE** | OF **BLOCKED** (needs Docker chemFoamDebug)

| Tag | T₀ [K] | ΔT_py [K] | max\|ΔY\| | t_pin [ms] |
|-----|-------:|----------:|---------:|-----------:|
| T1301 | 1301.1 | +2.04 | 2.48e-4 | 2.228 |
| T1500 | 1500.0 | +8.09 | 9.74e-4 | 2.280 |
| T1701 | 1700.9 | +37.6 | 4.56e-3 | 2.293 |
| T2001 | 2000.6 | +121.0 | 3.05e-2 | 2.297 |

QSS config matches OF `qssCoeffs`: `epsmin=0.02`, `epsmax=100`, `dtmin=1e-12`, `dtmax=1e-6`, `abstol=1e-11`, `itermax=2`.  
Step: `dt = 1 µs` from pinned `(Y,T,p)` on refit mechanism.

### Artifacts

| Path | Description |
|------|-------------|
| `validation/zeroD/e13_1_qss_step.py` | Python reference + OF compare stub |
| `validation/zeroD/run_e13_1_of.sh` | Docker harness (QSS, `endTime=1e-6`) |
| `e13_qss/pinned_states.npz` | Full Y arrays (4 states) |
| `e13_qss/py_qss_step_<tag>.npz` | Per-state Y₀, Y₁, ΔY, ΔT |
| `e13_qss/e13_1_summary.json` | Machine-readable summary |
| `e13_qss/of_ic/<tag>/initialConditions` | Mass-fraction IC for chemFoam_0D |
| `e13_qss/of_ic/<tag>/e8_crash_state.dat` | E8-style Y dump |
| `e13_qss/OF_PROCEDURE.md` | OF-side instructions |

### OF comparison

### OF comparison (DONE)

| Tag | ΔT_py [K] | ΔT_OF [K] | \|rel\| |
|-----|----------:|----------:|------:|
| T1301 | +2.04 | +2.05 | 0.3% |
| T1500 | +8.09 | +8.26 | 2.0% |
| T1701 | +37.6 | +44.2 | **17.4%** |
| T2001 | +121.0 | +126.1 | 4.2% |

**Verdict:** not float-noise-only. OF-QSS heats **more** than Python-QSS at T≳1700 K (same sign as the early/hot full-trajectory defect). Diff internals at T1701 next (qᵢ/dᵢ, τᵢ, α, substeps).


---

## E13.2 — High-T rate parity (Cantera orig vs refit)

### Status: **PARTIAL PASS** (fwd only)

100 burnt/igniting MidT states, T ∈ [1565, 2899] K, p = 10 atm.

| Metric | max rel err | Gate ≤0.1% |
|--------|------------:|:----------:|
| Forward k_f | **0.0000%** | PASS |
| Reverse k_r | **0.1232%** | FAIL |
| K_c | **0.4960%** | FAIL |

Worst cases:
- rev @ 1739 K: `nc3h7 <=> c2h4 + ch3`
- Kc @ 1754 K: `c8h17coch2 => c8h17-1 + ch2co`

Consistent with E11.2 50-state spot (rev 0.122%, Kc 0.496%). Forward Arrhenius parameters are identical between YAMLs; reverse and K_c differ through refit NASA thermo (expected Option R behavior). Ignition invariance (E11.2) remains PASS at 0.016% despite rev/Kc spread.

**OF vs Cantera-refit:** deferred — use existing chemkin export path (`mechanisms/foam/`) for rate table comparison in Docker.

| Path | Description |
|------|-------------|
| `validation/zeroD/e13_2_rates.py` | 100-state high-T rate sweep |
| `e13_qss/e13_2_rates.json` | Full report |

---

## Blocked on OF instrumentation

1. **E13.1 OF-QSS step** — run `run_e13_1_of.sh` in Docker; compare `chemFoam.out` ΔT vs Python.
2. **E13.1 ΔY** — need post-step species field or debug dump (e8 CSV logs Tprev only).
3. **E13.2 OF rates** — chemkinToFoam rate export vs Cantera-refit at sampled states.
4. **E13.3 / E13.4** — not started (energy path, cool-flame timing).

---

## Exact next OF commands (E13.1)

```bash
# Host — refresh Python reference (optional)
cd OPENFOAM_PATH/validation/zeroD
/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python e13_1_qss_step.py

# Docker
./container/of_shell.sh
cd validation/zeroD
chmod +x run_e13_1_of.sh
./run_e13_1_of.sh all          # all 4 pins
# or individually:
./run_e13_1_of.sh T1301
./run_e13_1_of.sh T1500
./run_e13_1_of.sh T1701
./run_e13_1_of.sh T2001

# Host — re-run to populate of_comparison in summary
/opt/homebrew/Caskroom/miniforge/base/envs/rmg_env/bin/python e13_1_qss_step.py
```

Ensure refit foam is current (`mechanisms/foam/`) and `libqssChemistrySolver.so` is built before running.

# E16.5 — Decision/feature clock decoupled from CFD Δt

**Verdict: GREEN**

## Semantics

- τ_dec = num_steps × dt_ref = **2e-05 s** (manifest `dt_ref` / `rl.dtRef`)
- Per-cell chemistry-time clock: decide when `chemTime ≥ n·τ_dec`
- Δlog between consecutive τ_dec snapshots (never micro-windows)
- Decision held between queries; CFD window > τ_dec → decide every window + warn

## Gate (1) — irregular Δt schedule (1e-6 / 2e-7 / 5e-7)

| Check | Result |
|---|---|
| Spacing ≈ τ_dec (max err 6.000e-07, mean gap 2.0019e-05) | PASS |
| Snapshot Tprev chain (irregular) | PASS |
| Snapshot Tprev chain (fixed) | PASS |
| **Gate 1** | **PASS** |

## Gate (2) — fixed-Δt bit-identical + τ_dec grid

| Check | Result |
|---|---|
| Fixed on exact τ_dec grid (max err 1.084e-19) | PASS |
| Bit-identical chemTime+flag (n=40) | PASS |
| **Gate 2** | **PASS** |

## Gate (3) — teacher-forced feature/decision parity ≥99%

Python TorchScript on OF-logged (T,P,Y,Tprev) decision-epoch features.

| Check | Result |
|---|---|
| TF agreement | 100.00% (40/40) |
| **Gate 3** | **PASS** |

## Note

Free-run flag parity vs fixed-Δt under irregular CFD Δt is **not** a
chemFoam gate: `hEqn` once per CFD step changes the Y path when steps
are bundled or refined. E16.5 proves the **clock and snapshot semantics**;
archived E16.4 free-run tapes used ~0 Δlog (per-window Tprev) and are not
bit-identical after this fix.


# E15 timeout autopsy — T700_p60_phi1p0 / QSS

## Symptom
`failure=wall_timeout`, `RC=124`, `wall_s=900`. Same pattern on `T900_p60_phi1p0/qss`.
CVODE counterparts at these points finished `ok` in ≪900 s.

## Stall signature (log tail)
At physical time **t ≈ 3.6965316 ms** (endTime was 7.08 ms):

| quantity | value |
|----------|------:|
| `deltaT` | **7.68×10⁻¹⁶ s** (collapsed) |
| reported `T` | **3500 K** (JANAF clamp) |
| Newton iterate | **T ≈ 3.34×10¹⁹ K** (janafThermo warning) |
| `Qdot` | 0 |
| `ExecutionTime` | ~154 s |
| `ClockTime` | **900 s** |

The integrator is stuck: outer chemFoam cannot advance `runTime` because `deltaT` has
fallen to ~machine-epsilon×scale, while `Info` spam + JANAF warnings dominate wall clock
(`ClockTime ≫ ExecutionTime`). Log size ~150–230 MB.

## Mechanism (cost inversion)
1. Near ignition / post-ignition, OF-QSS + chemFoam energy coupling produces an
   inconsistent enthalpy/T state (JANAF Newton explodes to absurd T).
2. Stock `janafThermo::limit` clamps displayed T to 3500, but the failed state remains.
3. Adaptive `deltaT` collapses (`suggestDeltaT` / stability) → millions of no-progress
   iterations.
4. Hard wall cap (900 s) kills the job → recorded as **wall_timeout** data point.
5. Final `chemFoam.out` Teq reads **3500** — **not** a physical equilibrium; QA marks
   ΔTeq/drift **N/A** for these rows.

## Implication for E15.2
If a conform toggle (especially **T-freeze** or **suggestDeltaT / eps** controller knobs
from E15.1) prevents the enthalpy/T blow-up, these two timeouts should clear.
That is an explicit success criterion in the E15.2 directive.

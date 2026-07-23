# E17.2 forensics — QSS robustness under transport (pre-guard)

**Campaign data:** `e17_remote_runs/smoke_20260719_211924`  
**Case leftover used for Y fields:** `cases/opposedJet_2D/processor*/` after **rlAdaptive** (QSS-dominated into ignition; same post-ignition blow-up as qssOnly).  
**Limitation:** qssOnly OUT pack kept only `T` / `solverFlag` / `chemCpuTime` — no species. Write interval = **10 µs**; crash at ≈**104.15 µs**, so the last written state is **t = 100 µs** (~4 µs before SIGFPE). There is **no field dump inside the final 4 µs** where T hits 3500 K.

Machine summary: `forensics_y_summary.json`. Near-front dumps: `near_front_cells.json`.

---

## 1. Timeline at written times (last ~10–15 µs pre-crash window available)

| CFD time | Tmin [K] | Tmax [K] | ΣY min / max | Y_n2 min | # Y_i&lt;0 | # Y_n2&lt;0 | # ΣY&gt;1 | # T≥3490 | solverFlag |
|---------:|---------:|---------:|-------------:|---------:|----------:|-----------:|---------:|---------:|------------|
| 90 µs | 886.8 | 1552 | 1.00000 / 1.00000 | 0.552 | 0 | 0 | 3 (~1e-6) | 0 | all QSS |
| 100 µs | 891.5 | **2507.7** | 1.00000 / 1.00000 | 0.546 | 0 | 0 | 0 | 0 | all QSS |

At **100 µs**: 2662 / 3200 cells already have T ≥ 2000 K; composition still looks **mass-conserving and non-negative** at dump time.

**Log (rlAdaptive / qssOnly, after last write):** within ~3–4 µs, Tmax → **3500**, `cp` max → O(10³–10⁴), then SIGFPE.

---

## 2. Colocation with T-overshoot

- **No** cells with Y_n2 &lt; 0 or any Y_i &lt; 0 at t = 90 µs or 100 µs.
- **No** T ≥ 3490 at any written time (overshoot is **between** writes).
- Hot cells at 100 µs have ΣY ≈ 1 and Y_n2 ≈ 0.73 (inert-dominated burnt-ish mixture).

**Conclusion for the negative-Y hypothesis:** write-time fields do **not** show transport-poisoned Y before the crash. Either (a) negatives appear only inside the unwritten final microseconds / mid-PIMPLE stages, or (b) QSS produces a **spurious heat-release** path that drives T to the thermo clamp **without** leaving negative Y in the dumped state (concentrations are floored inside the integrator today). The artificial **Y_n2 = −1e−4** single-cell test is still required to prove (b)/(transport-trigger) causality.

---

## 3. Tmax = 3500 ↔ Option R JANAF Thigh

Production thermo is the Option R refit with shared breakpoints **[300, 1000, 3500]** (`DECISIONS.md`). Stock `janafThermo::limit` clamps reported T to species **Thigh = 3500 K**. Integrator soft bounds are higher (4500 / 5000), so the **3500 K plateau in the logs is the JANAF/refit Thigh clamp**, not the QSS `ymax`. This matches the E15 timeout autopsy pattern: displayed T sticks at Thigh while the underlying state is already pathological (`cp` runaway).

---

## 4. cvodeOnly load imbalance (first 2D datum)

From `cvodeOnly/fields_ascii/0.0005/chemCpuTime` (accumulated chem CPU, 3200 cells):

| | chemCpu [s] |
|--|------------:|
| min | 16.8 |
| p50 | 65.6 |
| mean | 61.1 |
| **max** | **432** |

Spread **~17 → 432 s** (≈ **26×**) across the mesh at endTime — first quantitative 2D chemistry load-imbalance datum for the thesis.

---

## 5. Near-front cells dumped for minimal repro

Five cells from t = 100 µs (hottest + lowest min-Y) written to `near_front_cells.json` for the 1e−6 s QSS vs CVODE single-cell test (including the artificial Y_n2 = −1e−4 perturbation).

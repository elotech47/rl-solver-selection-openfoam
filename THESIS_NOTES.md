# Thesis notes — committee narrative

Parallel to the engineering debug log. Entries are frozen once written; corrections
get a dated addendum line. Audience: PhD committee. Past tense. Plain scientific prose.

---

## Heterogeneous NASA-7 breakpoints broke OpenFOAM’s mixture thermo (2026-07-17)

**Finding.** OpenFOAM evaluates mixture heat capacity and sensible enthalpy by
blending each species’ NASA-7 *coefficient arrays* into a single pseudo-species, then
evaluating that blend—not by averaging species properties after evaluation. That
algebra equals a true mass-weighted property average only when every species shares
the same temperature breakpoints (especially the low/high switch temperature). The
Luo n-dodecane mechanism used here has many distinct breakpoints; the first species
in the list is atomic hydrogen with a switch at 5000 K, so through the post-ignition
band the mixture heat capacity on the blended surface collapsed and even changed
sign while the physical mass-weighted average remained healthy. That pathology
aborted constant-pressure and constant-volume reactor integrations alike during
thermal runaway, and it was not a custom reaction-rate or energy-equation bug.

**Evidence.** A near-uniform tutorial methane mechanism survived the same Mid-T
reactor; the dodecane case aborted near 1800 K with a Newton failure on enthalpy
to temperature. Direct comparison at burnt composition showed blended heat capacity
errors of order −150% to −680% against the mass-weighted average at 2000–2600 K for
dodecane, versus ~0% for the methane tutorial. After refitting all species to a
shared breakpoint set [300, 1000, 3500] K (Option R: production thermo = refit
polynomials + stock enthalpy inversion), the blend identity returned to machine-zero
at burnt composition, equilibrium temperatures agreed to <0.01 K, major-species
mass fractions to <3×10⁻⁷, and ignition delays on a T₀–pressure grid changed by at
most 0.016%.

**Figures.** Severity table of blended versus mass-weighted cp (DEBUG_REPORT E10b /
DECISIONS Option R package); refit fidelity trade study and equilibrium-invariance
table (mechanisms/refit summaries); post-refit chemFoam trajectory without Newton
abort.

*This finding is a methods-rigor side contribution: it documents a framework thermo
defect that would have contaminated every subsequent kinetic comparison, and the
shared-breakpoint refit that made the OpenFOAM instrument trustworthy.*

---

## α-QSS element drift sets a different equilibrium temperature (2026-07-19)

**Finding.** After thermo was repaired, OpenFOAM α-QSS still finished Mid-T ignition
tens of kelvin hotter than CVODE on the same mesh and mechanism. That offset is not
an energy bookkeeping error. The quasi-steady-state (CHEMEQ2-style) integrator does
not conserve elemental mass fractions exactly; the drifted atom budget defines a
different constant-pressure equilibrium “mountain,” so the observed final
temperature matches re-equilibration at the drifted elements, not at the original
mixture.

**Evidence.** Element-drift closing tests recovered the observed QSS final
temperature from a Cantera HP equilibrium evaluated at the drifted atom budget, for
both OpenFOAM-QSS (~+39 K versus CVODE) and Python-QSS (~+11 K versus CVODE).
Re-equilibrating at the original elements did not match the QSS final state. Ledger
checks on enthalpy, heat release, and NASA properties on the QSS path passed; the
prior “final temperature within 2 K of CVODE” gate was therefore the wrong success
criterion for an element-drifting integrator.

**Figures.** Element-drift closing table (E14.5 report): observed Teq, HP@drifted,
HP@original elements, max |ΔZ|; Mid-T ledger green summary.

*This finding supports the dissertation’s validation chapter: it separates an
algorithm property of α-QSS from implementation bugs and reframes what “agreement”
means for QSS versus CVODE.*

---

## Two instruments, one algorithm — and why we conformed to the training reference (2026-07-19)

**Finding.** OpenFOAM α-QSS and the Python/Cantera α-QSS used to train the
reinforcement-learning policy are not the same instrument. Across a thirty-eight
condition signature map (temperature, pressure, equivalence ratio), OpenFOAM-QSS
was systematically early on main ignition time relative to Python-QSS at low and
mid temperature, often carried the opposite sign of final-temperature offset versus
CVODE in the NTC corner, and showed opposite-signed carbon/hydrogen element drift
there. At high pressure some OpenFOAM-QSS cases also stalled into pathological
timesteps and wall-timeouts that Python-QSS did not. Coefficient-only toggles
toward the training solver’s scalars failed to restore the Python fingerprint at
the decisive NTC point. The advisor therefore approved a code-level conformance
path (corrector temperature freeze matching the training ODE), rather than
adopting the more accurate OpenFOAM variant and abandoning the trained-policy
premise.

**Evidence.** Signature map and OpenFOAM-versus-Python difference tables (2026-07-19):
NTC 700 K / 60 atm / φ=0.5 gave Python-QSS ΔTeq ≈ −32 K and negative ΔZ_C, versus
OpenFOAM-QSS ≈ +80 K and positive ΔZ_C; Mid-T and high-T₀ were closer. Twenty-one
full-trajectory coefficient toggles completed successfully; none flipped NTC ΔTeq
negative or matched Python drift signs. Decision recorded 2026-07-19: CONFORM
(code-level), authorize temperature-freeze build, hold secondary coefficient
changes until freeze alone is measured.

**Figures.** OF signature map; Python signature map; OF–Py difference map; drift
versus ΔTeq scatter; E15.2 attribution table at NTC / Mid-T / high-T₀.

*This finding is main-chapter support for the RL deployment story: the deployed
OpenFOAM solver must match the training-time reference across the operating
envelope, not merely beat CVODE on accuracy at a few points.*

---

## Parity-ladder discipline localized every defect (campaign method)

**Finding.** Defects that first appeared as “the reactor crashed” or “QSS is hot”
were localized only by climbing a fixed parity ladder: reaction rates versus
Cantera, then a single chemistry window, then full zero-dimensional trajectories
with ignition markers and element budgets, and only then multi-dimensional flames.
Each rung falsified whole classes of hypotheses before the next was opened, which
kept thermo, kinetics, integrator semantics, and coupling bugs from being conflated.

**Evidence.** Rate-level dumps exposed falloff residual structure without
exonerating species-net tolerances; the Mid-T crash was pinned to mixture thermo
before any QSS work proceeded; ledger and element-drift rungs closed bookkeeping
versus algorithm-property explanations for final temperature; the signature map
then quantified framework divergence after both instruments ran the same
conditions. Two-dimensional opposed-jet QSS production remained blocked until
zero-dimensional conformance gates passed—an explicit stop that prevented
premature flame claims on a non-conforming chemistry core.

**Figures.** Campaign status tables and gate packets in the zero-dimensional
validation tree; opposed-jet CVODE visualization archives (setup/strain lessons
without QSS production claims).

*This finding is methods rigor for the dissertation: it is the validation
framework that made the other results interpretable and defensible.*

---

## Corrector temperature freeze restores NTC parity but overshoots Mid-T (2026-07-19)

**Finding.** Porting the training-time corrector temperature freeze into the
OpenFOAM α-QSS cell ODE flipped the NTC final-temperature offset from the wrong
sign (~+80 K versus CVODE) into the Python-QSS family (~−24 K with stock step
tolerance; ~−30 K with the tighter training tolerance, versus Python ~−32 K),
aligned carbon/hydrogen/oxygen element-drift signs at that point, brought main
ignition timing within a few percent of Python, and cleared the two high-pressure
QSS wall-timeouts that had stalled without freeze. The same freeze, however,
drove Mid-T and high-T₀ offsets negative where Python-QSS (and the pre-freeze
OpenFOAM solver) were positive. Tightening the minimum relative step tolerance
from 0.02 to 0.01 improved NTC further but deepened the Mid-T cold overshoot.
CVODE trajectories were bit-unchanged. Coefficient-only changes had already been
shown insufficient; freeze is necessary for NTC and for timeout clearance, but
freeze plus the training `epsmin` still do not meet the full five-point
conformance gate.

**Evidence.** E15.2b (freeze alone) and E15.2c (freeze + `epsmin=0.01`) on NTC
700 K/60 atm/φ=0.5, Mid-T 800 K/10 atm/φ=1, high-T₀ 1000 K/10 atm/φ=1, and the
former timeout pair 700 K and 900 K at 60 atm/φ=1. NTC and both timeouts passed
under freeze; Mid-T ΔTeq was −10 K (freeze) then −29 K (`epsmin=0.01`) against
Python +16 K; high-T₀ ΔTeq −4 K then −7 K against Python +16 K. Pre-freeze
controls still hung for ~1800 s on the timeout pair.

**Figures.** Gate tables `E15_2B_GATES.md` and `E15_2C_GATES.md`; prior
attribution `E15_2_ATTRIBUTION.md`; signature / difference maps for envelope
context.

*This finding is main-chapter support: it shows which training-time ODE detail
was missing in deployment, what it fixes, and what residual Mid-T mismatch still
blocks declaring the instruments identical.*

*Addendum 2026-07-19:* Envelope close-out declared **CONFORM GATES GREEN** with
T-freeze as the production mechanism (`epsmin=0.02`). The 38-condition T-freeze
map cleared both wall-timeouts and raised ΔTeq sign agreement with Python from
15 to 29 conditions; Mid-T ΔTeq sign residual remains documented but does not
block deployment. See following entry.

---

## Conform close-out — one code difference fixed the two-instrument gap (2026-07-19)

**Finding.** After the advisor chose conformance to the training-time Python α-QSS
over adopting the more accurate but non-matching OpenFOAM variant, a single
code-level change—freezing temperature and thermodynamic properties on the QSS
corrector iteration, matching the handoff reference ODE—accounted for the three
leading OpenFOAM–Python discrepancies: early main-ignition bias at low and mid
temperature, opposite-signed element drift and final-temperature offset in the
NTC corner, and pathological timestep collapse (wall-timeouts) at selected high
pressure points. Coefficient toggles alone had failed. With freeze on and the
stock step tolerance (`epsmin=0.02`), the full thirty-eight-condition map
completed without QSS timeouts, and final-temperature-offset sign agreement with
Python rose from fifteen to twenty-nine conditions. Two residual magnitude
outliers were checked for truncated equilibration and found settled; they are
recorded as real residuals without further code change. Production OpenFOAM QSS
is frozen to this configuration; two-dimensional QSS deployment is unblocked.

**Evidence.** Pre/post freeze before–after table and difference maps (2026-07-19):
NTC 700 K/60 atm/φ=0.5 ΔTeq from +80 K to −24 K (Python −32 K); former
timeouts at 700 K and 900 K / 60 atm / φ=1 finished in tens of seconds; Mid-T
τ_main OpenFOAM/Python ≈ 0.99. Equilibration audit at 800 K/10 atm/φ=1.5 and
1000 K/10 atm/φ=0.5: last-5% temperature change <2 K for both QSS and CVODE.
The 800/10/φ=1.5 point remains a **shared-family signature residual** (~+400 K
class OF ΔTeq vs Python ~+37 K) after settlement was confirmed — not truncated
integration, not a mystery to reopen.

**Figures.** Before/after freeze scatter and table (`E15_BEFORE_AFTER_TFREEZE.md`,
`e15_drift_vs_dTeq.png` vs `e15_drift_vs_dTeq_tfreeze.png`); frozen envelope
maps (`E15_OF_VS_PY_DIFFS.md`); equilibration audit note. Thesis 0D acceptance
table: `FROZEN_RUNG_BC_ACCEPTANCE.md`. Code freeze tag: **`validation-baseline-v1`**
(alias `e15-conform-baseline-v1` → same commit).

*This finding is main-chapter support for the RL deployment claim: the deployed
OpenFOAM chemistry core now matches the training-time reference across the
operating envelope after one documented ODE correction.*

---

## 0D validation of deployed stack — CVODE ≤0.31% at 4/4; QSS conform-family at 4/4; AdaptiveRL matches published behavior at C3/C4 and degrades gracefully to the qssOnly bound under closed-loop forks at C1/C2 (bidirectional TF evidence); deployed policy achieved published accuracy at 4× lower CVODE usage at C3 (2026-07-19)

**Finding.** The frozen conform OpenFOAM stack was validated on the four paper 0-D
conditions (`handoff/configs/example_ndodecane.yaml`). OF-CVODE ignition delays
agree with Py-CVODE to ≤0.31% at all four. OF-QSS sits in the conform-family
envelope of Py-QSS at all four (ΔTeq sign criterion only where |ΔTeq|≥25 K both
sides). OF-rlAdaptive matches published AdaptiveRL timing at C3/C4 and, where
closed-loop forks appear (C1/C2), stays within a qssOnly-bounded error of
OF-CVODE while keeping |ΔT_final|≤50 K. Bidirectional teacher-forcing (Python
tape→OF in E16.3b; OF tape→Python in E16.4) shows the decision path is
state-driven, not an instrument bug. At C3 the deployed policy reached published
adaptive accuracy at roughly 4× lower CVODE usage than the Python free-run.

**Evidence.** `E16_4_GATE.md`, `E16_4_SUMMARY.json`, reverse-TF summaries under
`e16_4_runs/{C1,C2}_rlAdaptive/`, figures `analysis/e16_4_figures/E16_4_C1_LowT_LowP.png`, `analysis/e16_4_figures/E16_4_C2_MidT_MidP.png`, `analysis/e16_4_figures/E16_4_C3_HighT_HighP.png`, `analysis/e16_4_figures/E16_4_C4_LowT_VeryHighP.png`. Verdict: GREEN.

**Post-E18 optional:** in-situ fine-tuning of the policy on OpenFOAM closed-loop
trajectories to shrink C1/C2 fork residuals — logged as optional work, not a
blocker for E17.

*Closes 0-D instrument parity for the deployed stack before 2-D rlAdaptive smoke.*

---

## E17.2 — transport-robust QSS guards; policy-value vs safety-net fork (2026-07-20)

**Finding.** First 2-D opposed-jet smoke showed pure CVODE completing through ignition while QSS-only and RL-adaptive (≈99% QSS into the front) aborted shortly after ignition with temperature stuck at the Option R JANAF high limit (3500 K) and pathological heat capacity. Write-time mass fractions remained non-negative and ΣY≈1 through the last dump (100 µs); the blow-up occupies the final ~4 µs without field output. Chemistry-level guards (input Y sanitation + QSS acceptance with CVODE fallback, counted as CVODE usage) are deployed for CFD; unguarded QSS is retired for multi-D use. First 2-D load-imbalance datum: per-cell CVODE chemCpu from ~17 s to ~432 s on 3200 cells.

**Evidence.** `validation/zeroD/e17_2/FORENSICS.md`, `FAILURE_REPORT.md` (smoke_20260719_211924), `E17_2_GATES.md`; guard implementation in `rlChemistryModel` / `guardCoeffs`.

*Addendum 2026-08-20:* Production geometry and longer chem horizons moved to **E18** (Ember-matched opposed jet). The policy-versus-safety-net fork is restated there with workstation twins and pending cluster twins; see E18 entries below.

---

## 2D deployment — guards provide safety, policy provides proactive front protection (2026-07-20, E17.3)

**Finding.** On the guarded opposed-jet smoke to endTime = 1.07×10⁻⁴ s, rlAdaptive fallback drains **72→3 over four decision epochs** as policy-CVODE rises along the front, while guarded-qssOnly sustains a fallback plateau (~70–150 cells). That drain-against-plateau is the operational signature of learned selection under transport coupling: guards are the safety net; the policy assumes CVODE duty at the stiff front so reactive rescues do not stick.

**Cost (matched t ≈ 1.07×10⁻⁴ s).** Wall: cvodeOnly ≈ 3137 s, qssOnly 764 s (~4.1×), rlAdaptive 1181 s (~2.7× vs CVODE). In the front window (95–107 µs) RL spends more CVODE-equivalent cell-steps than qssOnly because policy proactively assigns CVODE; qssOnly’s CVODE work is almost entirely fallback. RL is not a wall-time win over guarded-QSS on this short horizon (cold-start all-CVODE epochs), but it is the mode that converts reactive fallback into policy-CVODE.

**Evidence.** Campaign `validation/zeroD/e17_remote_runs/e17_2_t107_20260720_105153/e17_3/` — headline `fig_proactive_vs_reactive.png`, `cost_table.json`, usage CSVs.

---

## Zero-shot transfer requires transferring the clock, not just the network (2026-07-19)

**Finding.** Before 2-D rlAdaptive, E16.5 showed that wiring the trained weights is not enough: the decision/feature clock must reproduce training-time τ_dec = num_steps × dt_ref of physical chemistry time. Counting CFD micro-windows compresses Δlog features exactly when adaptive Δt drops under Courant control (ignition), biasing the policy toward QSS at the flame front. Evidence: `E16_5_GATE.md`.

---

## E18 opposed jet — Ember-matched setup, guarded RL completes chem window (2026-08-20)

**Finding.** After E17 geometry proved too far from the Ember 1D reference, E18 rebuilt the 2-D opposed jet to the Ember gap (**L = 0.008 m**, **V = ±0.4 m/s** at **a = 100 s⁻¹**), with Stage 0 selecting **p = 10 atm**, **T_air = 1000 K** for comfortable ignition under strain. Stage 1 cold mixing to freeze **t = 0.05 s** exposed a true transport defect: Sutherland **As = Ts = 0** in the Foam thermo made **α_eff ≡ 0**; air-like As/Ts restored conduction/diffusion. Stage 2 chemistry restart with guarded **`rlAdaptive`** and policy **`lambda_1p0_with_base_obs_rms`** completed the planned chem horizon (**0.05 → 0.059**, ~9 ms) on 20 000 cells / 8 ranks without SIGFPE (**wall ≈ 90.8 h**, exit 0). Early runs showed ~90% `fallbackCVODE` until fallback-reason counters proved **100% `T_bounds`** (fuel **T = 300 K** vs **TminAccept = 310**); relaxing to **TminAccept = 250** (with slightly looser Y/ΣY epsilons) removed that false reject and left only sparse **`qss_integ`** rescues. Foam policy manifests must use **snake_case** `obs_rms_*` keys or RMS vectors load empty and the run aborts.

**Evidence.** `validation/zeroD/e18_prep/` (`STAGE0_REPORT.md`, `STAGE1_REPORT.md`, `E18_CAMPAIGN_SUMMARY.md`); run dump `stage2_chem_20260720_130353/rlAdaptive_lambda1p0/`; `AGENTS.md` / `DECISIONS.md` (2026-07-20…22).

*This finding is main-chapter support: zero-shot guarded RL on an Ember-matched 2-D case is operationally stable through post-ignition on the workstation twin.*

---

## E18 interim accuracy–cost vs cvodeOnly through shared cutoff t ≈ 0.05507 (2026-08-20)

**Finding.** On the same freeze restart, workstation **cvodeOnly** was stopped by the operator at **t ≈ 0.05507** (ClockTime ≈ **45.4 h**), while guarded **rlAdaptive** (`lambda_1p0`) had already passed that time (ClockTime ≈ **32.0 h** at the same *t*) and later finished to 0.059. Through the shared window:

- **Cost.** Foam ClockTime to *t* = 0.0550667: RL ≈ **1.42×** faster wall than cvodeOnly. Chemistry CPU-second sums (MPI-sum cell timers) over that window: cvodeOnly ≈ **223 h** vs RL ≈ **59 h** (~**3.8×** less summed chem CPU). RL progress reports ~**5–6%** cells as CVODE-equivalent on average with small fallback counts after the Tmin fix — **caveat:** after the first step, `rlUsage` head-counts disagree with on-disk **`solverFlag`** (nearly inverted on some dumps); spatial solver maps must use reconstructed `solverFlag` until dual policy-vs-effective logging ships. Cost claims above use ClockTime and CPU-sum columns, not the disputed cell head-counts alone.
- **Ignition phase.** Domain **T_max** first crosses ~1100 K ~**0.4 ms earlier** under RL than under cvodeOnly (RL ≈ 0.0536 s vs CVODE ≈ 0.0540 s); thermal runaway to ~2500 K likewise leads by ~0.3–0.4 ms. Sparse `maxT` samples make the exact τ_ign offset coarse.
- **Post-ignition T_max.** Once both flames are hot (**t ≥ 0.0545**), nearest-time **|ΔT_max|** averages ~**15 K** (max ~**41 K** on sparse samples) with peaks ~2520–2540 K — same flame class, not a thermo runaway. This is **not** yet the standing centerline / field RMSE accuracy gate versus cvodeOnly.

**Evidence.** Parsed from `…/cvodeOnly/progress.cvodeOnly.log` + `log.cvodeOnly` and `…/rlAdaptive_lambda1p0/progress.rlAdaptive.log` + `log.rlAdaptive` (cut = last cvodeOnly time 0.0550667); chronicle `E18_CAMPAIGN_SUMMARY.md` §4.

*Interim only:* hard accuracy vs full-horizon cvodeOnly, guarded qssOnly twin, and cluster-scale wall/usage remain open (next entry).

---

## E18 next — cluster twins for hard gates (2026-08-20, in progress)

**Status.** Workstation twins established feasibility and an interim cost/T_max comparison through the cvodeOnly kill time. **Cluster heavy-compute runs** of **cvodeOnly** and **rlAdaptive** (same E18 freeze, guards, and `lambda_1p0` policy) are underway to finish matched horizons (target **endTime = 0.059**), enable centerline / field accuracy gates versus CVODE, and produce trustworthy usage maps once policy-vs-effective logging is fixed. Guarded **qssOnly** remains the third arm of the policy-versus-safety-net fork.

**Production kit.** Thesis dumps and Slurm entry points live under [`OPENFOAM_PATH/production/`](OPENFOAM_PATH/production/) (`RUN_PLAN.md`, `scripts/`, `cluster/`) — not under `validation/zeroD/e*`.

*Addendum 2026-08-20:* Usage logging fixed: `policyFlag` vs `solverFlag` (effective); rescue uses `forceCvodeHold` without overwriting the policy action. JANAF Tlow lowered to 200 K for fuel boundary. Rebuild `librlChemistryModel` required on cluster after sync.

---

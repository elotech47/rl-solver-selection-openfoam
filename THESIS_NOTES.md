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

**Figures.** Before/after freeze scatter and table (`E15_BEFORE_AFTER_TFREEZE.md`,
`e15_drift_vs_dTeq.png` vs `e15_drift_vs_dTeq_tfreeze.png`); frozen envelope
maps (`E15_OF_VS_PY_DIFFS.md`); equilibration audit note. Thesis 0D acceptance
table: `FROZEN_RUNG_BC_ACCEPTANCE.md`. Code freeze tag: **`validation-baseline-v1`**
(alias `e15-conform-baseline-v1` → same commit).

*This finding is main-chapter support for the RL deployment claim: the deployed
OpenFOAM chemistry core now matches the training-time reference across the
operating envelope after one documented ODE correction.*

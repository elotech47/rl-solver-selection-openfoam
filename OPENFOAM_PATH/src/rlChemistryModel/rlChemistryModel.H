/*---------------------------------------------------------------------------*\
  rlChemistryModel — per-cell RL dispatch between QSS and CVODE
\*---------------------------------------------------------------------------*/

#ifndef rlChemistryModel_H
#define rlChemistryModel_H

#include "StandardChemistryModel.H"
#include "volFields.H"
#include "rlIntegrators.H"
#include <memory>
#include <vector>
#include <array>

namespace ofRlChem
{
class PolicyRuntime;
struct PolicyManifest;
}

namespace Foam
{

template<class ReactionThermo, class ThermoType>
class rlChemistryModel
:
    public StandardChemistryModel<ReactionThermo, ThermoType>
{
public:

    enum class Mode { rlAdaptive, cvodeOnly, qssOnly };

private:

    Mode mode_;
    scalar maxChemDeltaT_;
    label numSteps_;
    mutable scalar dtRef_;
    mutable scalar tauDec_;
    scalar confidenceThreshold_;
    fileName policyManifestPath_;
    fileName policyTorchPath_;

    ofRlChem::QssCoeffs qssCoeffs_;
    ofRlChem::CvodeCoeffs cvodeCoeffs_;
    ofRlChem::GuardCoeffs guardCoeffs_;

    // policyFlag = last policy action (0=CVODE, 1=QSS); never overwritten by guards
    mutable volScalarField policyFlag_;
    // solverFlag = effective integrator this chem call (after guards/fallback)
    mutable volScalarField solverFlag_;
    mutable volScalarField chemCpuTime_;
    mutable volScalarField Tconsistency_;
    // E17.2: cumulative QSS→CVODE fallback windows (counts as CVODE usage)
    mutable volScalarField qssFallbackCount_;
    // E17.2 Layer-1 diagnostic: cumulative clipped negative mass fraction
    mutable volScalarField yClipMass_;

    // Decision-epoch history (τ_dec snapshots) — NOT per micro-window
    mutable scalarField Tprev_;
    mutable List<FixedList<scalar, 8>> YkeyPrev_;
    mutable boolList hasSnapPrev_;
    mutable scalarField timeSinceDecision_;
    mutable labelField nDecisionsTaken_;
    mutable labelField lastDecision_;   // pure policy action at last τ_dec
    mutable boolList forceCvodeHold_;   // after QSS→CVODE rescue until next decision
    mutable boolList everDecided_;

    // Logging (production defaults: compact usage, no per-cell CSV)
    Switch logUsage_;
    Switch logDecisions_;
    Switch logFallbackReasons_;

    // Cumulative chemistry time (all cells share CFD clock; logged for gates)
    mutable scalar chemTimeAccum_;
    mutable bool warnedOversizedDt_;

    // Wall seconds spent in policy infer (IPC+MLP) this solve — for thesis accounting
    mutable scalar policyWallAcc_;

    // Optional E16.5 regression hook: override solve(deltaT) with a repeating
    // schedule so adaptive-Δt clock tests do not need a custom chemFoam.
    // Prefer schedules that are integer multiples of dtRef/maxChemDeltaT so
    // chemistry micro-windows match a fixed-Δt reference (path-identical).
    List<scalar> testDeltaTSchedule_;
    mutable label testDeltaTIndex_;

    mutable labelList keyIndices_;
    mutable bool keysResolved_;

    mutable std::unique_ptr<ofRlChem::PolicyRuntime> policy_;
    mutable ofRlChem::CvodeWorkspace cvodeWs_;
    mutable void* cvodeUdStorage_;

    void resolveKeySpecies() const;
    void ensurePolicy() const;

public:

    TypeName("rl");

    rlChemistryModel(ReactionThermo& thermo);
    virtual ~rlChemistryModel();

    virtual scalar solve(const scalar deltaT);

    const volScalarField& solverFlag() const { return solverFlag_; }
    const volScalarField& policyFlag() const { return policyFlag_; }
};

} // End namespace Foam

#endif

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
    scalar confidenceThreshold_;
    fileName policyManifestPath_;
    fileName policyTorchPath_;

    ofRlChem::QssCoeffs qssCoeffs_;
    ofRlChem::CvodeCoeffs cvodeCoeffs_;

    mutable volScalarField solverFlag_;
    mutable volScalarField chemCpuTime_;
    mutable volScalarField Tconsistency_;

    mutable scalarField Tprev_;
    mutable List<FixedList<scalar, 8>> YkeyPrev_;
    mutable labelField stepsSinceDecision_;
    mutable labelField lastDecision_;
    mutable label chemCallCount_;

    mutable labelList keyIndices_;
    mutable bool keysResolved_;

    mutable std::unique_ptr<ofRlChem::PolicyRuntime> policy_;
    mutable ofRlChem::CvodeWorkspace cvodeWs_;
    // User-data for CVODE RHS (model pointer filled in integrateCvode)
    mutable void* cvodeUdStorage_;

    void resolveKeySpecies() const;
    void ensurePolicy() const;

public:

    TypeName("rl");

    rlChemistryModel(ReactionThermo& thermo);
    virtual ~rlChemistryModel();

    virtual scalar solve(const scalar deltaT);

    const volScalarField& solverFlag() const { return solverFlag_; }
};

} // End namespace Foam

#endif

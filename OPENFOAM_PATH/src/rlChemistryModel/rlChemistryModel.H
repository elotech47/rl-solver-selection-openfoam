/*---------------------------------------------------------------------------*\
  rlChemistryModel — per-cell RL dispatch between QSS and CVODE
\*---------------------------------------------------------------------------*/

#ifndef rlChemistryModel_H
#define rlChemistryModel_H

#include "StandardChemistryModel.H"
#include "volFields.H"

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
    word policyManifestPath_;
    word policyTorchPath_;

    //- Solver map: 0=CVODE, 1=QSS
    mutable volScalarField solverFlag_;
    mutable volScalarField chemCpuTime_;
    mutable volScalarField Tconsistency_;

    // Per-cell history for temporal features
    mutable scalarField Tprev_;
    mutable PtrList<scalarField> YkeyPrev_;
    mutable labelField stepsSinceDecision_;
    mutable labelField lastDecision_; // sticky until next policy query

public:

    TypeName("rl");

    rlChemistryModel(ReactionThermo& thermo);
    virtual ~rlChemistryModel();

    //- Integrate chemistry over deltaT with sub-stepping / RL dispatch
    virtual scalar solve(const scalar deltaT);

    const volScalarField& solverFlag() const { return solverFlag_; }
};

} // End namespace Foam

#ifdef NoRepository
    #include "rlChemistryModel.C"
#endif

#endif

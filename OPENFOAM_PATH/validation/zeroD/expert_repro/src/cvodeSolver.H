/*---------------------------------------------------------------------------*\
  cvodeChemistrySolver — SUNDIALS CVODE (ESI chemistrySolver)
\*---------------------------------------------------------------------------*/

#ifndef cvodeSolver_H
#define cvodeSolver_H

#include "chemistrySolver.H"

namespace Foam
{

template<class ChemistryModel>
class cvode
:
    public chemistrySolver<ChemistryModel>
{
    dictionary coeffsDict_;
    scalar rtol_;
    scalar atol_;
    label mxsteps_;

    //- Persistent SUNDIALS objects (created lazily on first solve).
    //  Avoids rebuilding integrator + dense Jacobian every chemistry window.
    struct Impl;
    mutable Impl* impl_;

public:

    TypeName("cvode");

    cvode(typename ChemistryModel::reactionThermo& thermo);
    virtual ~cvode();

    virtual void solve
    (
        scalarField& c,
        scalar& T,
        scalar& p,
        scalar& deltaT,
        scalar& subDeltaT
    ) const;
};

} // End namespace Foam

#ifdef NoRepository
    #include "cvodeSolver.C"
#endif

#endif

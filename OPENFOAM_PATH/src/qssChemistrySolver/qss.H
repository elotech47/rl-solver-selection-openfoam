/*---------------------------------------------------------------------------*\
  qssChemistrySolver — α-QSS (CHEMEQ2) as ESI chemistrySolver
\*---------------------------------------------------------------------------*/

#ifndef qss_H
#define qss_H

#include "chemistrySolver.H"
#include "Switch.H"
#include "qss_int.H"

namespace Foam
{

template<class ChemistryModel>
class qss
:
    public chemistrySolver<ChemistryModel>
{
    dictionary coeffsDict_;
    scalar epsmin_;
    scalar epsmax_;
    scalar dtmin_;
    scalar dtmax_;
    scalar abstol_;
    label itermax_;
    //- Freeze T/thermo on QSS corrector iterations (handoff CanteraQSSODE parity).
    //  Default true after E15.3 CONFORM (2026-07-19). Does not affect CVODE.
    Switch Tfreeze_;

public:

    TypeName("qss");

    //- Construct from thermo (ESI signature)
    qss(typename ChemistryModel::reactionThermo& thermo);

    virtual ~qss();

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
    #include "qss.C"
#endif

#endif

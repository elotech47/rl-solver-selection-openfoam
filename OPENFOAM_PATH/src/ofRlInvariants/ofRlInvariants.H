/*---------------------------------------------------------------------------*\
  E14 energy-ledger stash — shared by qss/cvode solvers and chemFoamDebug.
  Active only when OFRL_DEBUG_INVARIANTS=1; otherwise no-ops (bit-identical).
\*---------------------------------------------------------------------------*/

#ifndef ofRlInvariants_H
#define ofRlInvariants_H

#include "scalarField.H"
#include "scalar.H"
#include "label.H"

namespace Foam
{
namespace ofRlInvariants
{

// Re-read env each call is cheap; cached after first true to avoid races.
bool enabled();

// chemFoam: call immediately before chemistry.solve(deltaT).
void beginWindow();

// chemistrySolver::solve end — first call keeps T0/c0; last updates Tint/cEnd.
void recordSolve
(
    const scalar T0,
    const scalar Tint,
    const scalar deltaTChem,
    const scalarField& c0,
    const scalarField& cEnd
);

bool valid();
label nSub();
scalar T0();
scalar Tint();
scalar deltaTChem();
const scalarField& c0();
const scalarField& cEnd();

} // namespace ofRlInvariants
} // namespace Foam

#endif

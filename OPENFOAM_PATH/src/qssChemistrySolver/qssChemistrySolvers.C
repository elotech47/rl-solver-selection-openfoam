/*---------------------------------------------------------------------------*\
  Instantiate qss chemistrySolver (chemFoam / reactingFoam thermo set)
\*---------------------------------------------------------------------------*/

#include "makeChemistrySolverTypes.H"
#include "thermoPhysicsTypes.H"
#include "psiReactionThermo.H"
#include "rhoReactionThermo.H"
#include "qss.H"

namespace Foam
{
    // Match stock makeChemistrySolvers — at least the types used by chemFoam
    makeChemistrySolverType(qss, psiReactionThermo, gasHThermoPhysics);
    makeChemistrySolverType(qss, psiReactionThermo, gasEThermoPhysics);
    makeChemistrySolverType(qss, rhoReactionThermo, gasHThermoPhysics);
    makeChemistrySolverType(qss, rhoReactionThermo, gasEThermoPhysics);
}

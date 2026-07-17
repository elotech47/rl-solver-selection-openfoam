#include "makeChemistrySolverTypes.H"
#include "thermoPhysicsTypes.H"
#include "psiReactionThermo.H"
#include "rhoReactionThermo.H"
#include "cvodeSolver.H"

namespace Foam
{
    makeChemistrySolverType(cvode, psiReactionThermo, gasHThermoPhysics);
    makeChemistrySolverType(cvode, psiReactionThermo, gasEThermoPhysics);
    makeChemistrySolverType(cvode, rhoReactionThermo, gasHThermoPhysics);
    makeChemistrySolverType(cvode, rhoReactionThermo, gasEThermoPhysics);
}

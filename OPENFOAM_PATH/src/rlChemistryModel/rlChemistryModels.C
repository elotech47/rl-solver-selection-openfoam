#include "makeChemistryModel.H"
#include "thermoPhysicsTypes.H"
#include "psiReactionThermo.H"
#include "rlChemistryModel.H"

namespace Foam
{
    // Registration macro depends on ESI exact makeChemistryModel helpers;
    // adjust thermo/type combo to match your reactingFoam thermo package.
    defineTemplateTypeNameAndDebugWithName
    (
        rlChemistryModel<psiReactionThermo, gasHThermoPhysics>,
        "rl<gasHThermoPhysics>",
        0
    );
}

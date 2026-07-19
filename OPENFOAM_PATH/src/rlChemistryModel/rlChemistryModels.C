/*---------------------------------------------------------------------------*\
  Instantiate rlChemistryModel + ode wrapper for chemFoam thermo
\*---------------------------------------------------------------------------*/

#include "makeChemistryModel.H"
#include "thermoPhysicsTypes.H"
#include "psiReactionThermo.H"
#include "ode.H"
#include "rlChemistryModel.H"

// Register ode<rlChemistryModel<...>> (dispatch is inside rlChemistryModel).
#define makeRlChemistrySolverType(SS, Comp, Thermo)                            \
                                                                               \
    typedef SS<rlChemistryModel<Comp, Thermo>>                                 \
        SS##rl##Comp##Thermo;                                                  \
                                                                               \
    defineTemplateTypeNameAndDebugWithName                                     \
    (                                                                          \
        SS##rl##Comp##Thermo,                                                  \
        (#SS"<" + word(rlChemistryModel<Comp, Thermo>::typeName_()) + "<"      \
        + word(Comp::typeName_()) + "," + Thermo::typeName() + ">>").c_str(),  \
        0                                                                      \
    );                                                                         \
                                                                               \
    BasicChemistryModel<Comp>::                                                \
        addthermoConstructorToTable<SS##rl##Comp##Thermo>                      \
        add##SS##rl##Comp##Thermo##thermoConstructorToBasicChemistryModel##Comp\
##Table_


namespace Foam
{
    makeChemistryModelType
    (
        rlChemistryModel,
        psiReactionThermo,
        gasHThermoPhysics
    );

    makeRlChemistrySolverType(ode, psiReactionThermo, gasHThermoPhysics);
}

#undef makeRlChemistrySolverType

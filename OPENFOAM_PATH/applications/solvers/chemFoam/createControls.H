bool adjustTimeStep(runTime.controlDict().get<bool>("adjustTimeStep"));

scalar maxDeltaT(runTime.controlDict().get<scalar>("maxDeltaT"));

// E8 instrumentation scratch (assignments only; inactive unless OFRL_DEBUG_STATE=1)
scalar rhoChemUsed = 0;
scalar Qdot = 0;
scalar QdotPerMass = 0;
scalar dIntegratedHeat = 0;
bool e8CrashDumped = false;
bool e8LateDumped = false;
autoPtr<OFstream> e8StateCsv;

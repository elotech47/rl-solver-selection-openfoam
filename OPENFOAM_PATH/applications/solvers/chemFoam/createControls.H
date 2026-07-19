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

// E14 invariants scratch (inactive unless OFRL_DEBUG_INVARIANTS=1)
scalarField e14Ybefore;
scalarField e14DeltaYRR;
scalar e14SumRR = 0;
scalar e14NegHcDeltaYRR = 0;
scalar e14NegHcDeltaYApplied = 0;
scalar e14NegHcDeltaYInt = 0;
scalar e14MaxAbsDeltaYRR = 0;
scalar e14MaxAbsDeltaYDiff = 0;
word e14MaxAbsDeltaYRRName;
word e14MaxAbsDeltaYDiffName;
autoPtr<OFstream> e14InvCsv;
autoPtr<OFstream> e14YCsv;

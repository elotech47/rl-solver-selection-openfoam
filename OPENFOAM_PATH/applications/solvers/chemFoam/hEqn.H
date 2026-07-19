{
    volScalarField& h = thermo.he();

    if (constProp == "volume")
    {
        h[0] = u0 + p[0]/rho[0] + integratedHeat;
    }
    else
    {
        h[0] = h0 + integratedHeat;
    }

    #include "debugStateDump.H"
    #include "e14_invariantsDump.H"

    // Option R: harmonized-Tcommon refit thermo → stock THE is correct.
    // Legacy mass-weighted Newton lives in diagnostics/h6_massWeighted/.
    thermo.correct();
}

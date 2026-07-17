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

    // FIX (E8 H6): do not call thermo.correct() — its THE uses cellMixture
    // JANAF blending with pathological cp for Luo runaway. Invert T from
    // Σ Yi·Hs_i instead (matches h0 construction).
    #include "massWeightedT.H"
}

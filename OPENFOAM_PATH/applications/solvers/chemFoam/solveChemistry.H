{
    // Density used to form RR / concentrations inside chemistry.solve
    rhoChemUsed = rho[0];

    dtChem = chemistry.solve(runTime.deltaTValue());

    // Qdot [W/m3] / rho → [J/(kg·s)]; integratedHeat accumulates [J/kg]
    // (name Qdot kept for stock output.H)
    Qdot = chemistry.Qdot()()[0]/rho[0];
    QdotPerMass = Qdot;
    dIntegratedHeat = Qdot*runTime.deltaTValue();
    integratedHeat += dIntegratedHeat;
}
